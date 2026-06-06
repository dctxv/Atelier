"""Latency instrumentation (Part 1.7) — the backbone of Part 4 testing.

Design choice: per-request timings go into in-memory rolling buffers, NOT a DB
write per request. Writing a row on every request would amplify writes on the
hot path and pollute the single-writer queue under a benchmark — exactly the
thing we are trying to measure. Buffers give O(1) recording and instant
percentiles; a periodic flush persists samples to request_timing for durability.

Job timings are low-volume, so those write straight to job_timing.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from . import db

_MAX = 5000  # samples kept per path in memory

_req_buffers: dict[str, deque] = defaultdict(lambda: deque(maxlen=_MAX))
_pending: list[tuple] = []  # rows awaiting flush to request_timing


def record_request(path: str, method: str, status: int, duration_ms: float):
    _req_buffers[path].append(duration_ms)
    _pending.append((path, method, status, duration_ms, int(time.time())))


def _percentiles(values: list[float]) -> dict:
    if not values:
        return {"count": 0}
    s = sorted(values)
    n = len(s)

    def pct(p):
        idx = min(n - 1, int(round((p / 100) * (n - 1))))
        return round(s[idx], 2)

    return {
        "count": n,
        "p50": pct(50),
        "p95": pct(95),
        "p99": pct(99),
        "max": round(s[-1], 2),
    }


def summary() -> dict:
    paths = {p: _percentiles(list(b)) for p, b in _req_buffers.items() if b}
    all_vals: list[float] = []
    for b in _req_buffers.values():
        all_vals.extend(b)
    return {"overall": _percentiles(all_vals), "paths": paths}


async def flush_pending():
    """Persist buffered request timings to the DB (called periodically)."""
    global _pending
    if not _pending:
        return
    rows, _pending = _pending, []
    await db.executemany(
        "INSERT INTO request_timing(path, method, status, duration_ms, at) VALUES(?,?,?,?,?)",
        rows,
    )


async def record_job(job_type: str, duration_ms: float, queue_wait_ms: float):
    await db.execute(
        "INSERT INTO job_timing(type, duration_ms, queue_wait_ms, at) VALUES(?,?,?,?)",
        (job_type, duration_ms, queue_wait_ms, int(time.time())),
    )


async def job_summary() -> dict:
    rows = await db.fetchall(
        "SELECT type, duration_ms, queue_wait_ms FROM job_timing ORDER BY id DESC LIMIT 5000"
    )
    by_type: dict[str, dict[str, list]] = {}
    for r in rows:
        d = by_type.setdefault(r["type"], {"dur": [], "wait": []})
        d["dur"].append(r["duration_ms"])
        d["wait"].append(r["queue_wait_ms"])
    out = {}
    for t, d in by_type.items():
        out[t] = {
            "duration_ms": _percentiles(d["dur"]),
            "queue_wait_ms": _percentiles([w for w in d["wait"] if w is not None]),
        }
    return out
