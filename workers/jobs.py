"""Background job queue + worker loop (Part 1.4).

  - jobs(id, type, status, payload, attempts, last_error, created_at, finished_at)
  - Worker tasks consume queued jobs; APScheduler runs periodic ones.
  - Jobs are claimed atomically. Because every write goes through the single
    writer thread (services/db.py), the claim UPDATE can't race: two workers
    never grab the same job.
  - Restart-safety: on startup anything left 'running' is requeued.
  - Every job records duration_ms and queue_wait_ms (Part 1.7 / Part 4).
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from services import db, metrics

MAX_ATTEMPTS = 3
WORKER_COUNT = 2

_handlers: dict[str, callable] = {}
_workers: list[asyncio.Task] = []
_scheduler: AsyncIOScheduler | None = None
_running = False


def register(job_type: str):
    """Decorator: register an async handler(payload: dict) for a job type."""
    def deco(fn):
        _handlers[job_type] = fn
        return fn
    return deco


async def enqueue(job_type: str, payload: dict | None = None) -> str:
    job_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO jobs(id, type, status, payload, attempts, created_at) "
        "VALUES(?,?,?,?,?,?)",
        (job_id, job_type, "queued", json.dumps(payload or {}), 0, db.now()),
    )
    return job_id


async def _claim() -> dict | None:
    def op(conn):
        row = conn.execute(
            "SELECT * FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1"
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE jobs SET status='running', attempts=attempts+1 WHERE id=?", (row["id"],)
        )
        return dict(row)

    return await db.write(op)


async def _finish(job_id: str, status: str, error: str | None = None):
    await db.execute(
        "UPDATE jobs SET status=?, last_error=?, finished_at=? WHERE id=?",
        (status, error, db.now(), job_id),
    )


async def _process(job: dict):
    handler = _handlers.get(job["type"])
    queue_wait_ms = max(0.0, (time.time() - job["created_at"]) * 1000)
    started = time.perf_counter()
    try:
        if handler is None:
            raise RuntimeError(f"no handler registered for job type '{job['type']}'")
        payload = json.loads(job["payload"] or "{}")
        await handler(payload)
        await _finish(job["id"], "done")
    except Exception as e:  # noqa: BLE001
        if job["attempts"] >= MAX_ATTEMPTS:
            await _finish(job["id"], "error", str(e))
        else:
            await db.execute(
                "UPDATE jobs SET status='queued', last_error=? WHERE id=?", (str(e), job["id"])
            )
    finally:
        duration_ms = (time.perf_counter() - started) * 1000
        await metrics.record_job(job["type"], duration_ms, queue_wait_ms)


async def _worker_loop():
    while _running:
        job = await _claim()
        if job is None:
            await asyncio.sleep(0.25)
            continue
        await _process(job)


async def _requeue_stuck():
    """Restart-safety: jobs left mid-flight become queued again."""
    await db.execute("UPDATE jobs SET status='queued' WHERE status='running'")


async def start():
    global _running, _scheduler
    if _running:
        return
    _running = True
    await _requeue_stuck()
    for _ in range(WORKER_COUNT):
        _workers.append(asyncio.create_task(_worker_loop()))

    _scheduler = AsyncIOScheduler()
    # Persist buffered request timings periodically (Part 1.7).
    _scheduler.add_job(metrics.flush_pending, "interval", seconds=30, id="metrics_flush")
    # Periodic hooks registered by features (consolidation, email poll) attach
    # via add_periodic() before/after start.
    for spec in _pending_schedules:
        _scheduler.add_job(**spec)
    _scheduler.start()


_pending_schedules: list[dict] = []


def add_periodic(func, *, seconds: int, job_id: str):
    """Register a periodic job. Works before or after start()."""
    spec = {"func": func, "trigger": "interval", "seconds": seconds, "id": job_id}
    if _scheduler is not None:
        _scheduler.add_job(**spec)
    else:
        _pending_schedules.append(spec)


async def stop():
    global _running
    _running = False
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
    for w in _workers:
        w.cancel()
    _workers.clear()


async def stats() -> dict:
    rows = await db.fetchall("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status")
    depth = await db.fetchone("SELECT COUNT(*) AS n FROM jobs WHERE status='queued'")
    return {
        "by_status": {r["status"]: r["n"] for r in rows},
        "queue_depth": depth["n"] if depth else 0,
    }
