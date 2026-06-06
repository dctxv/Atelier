"""Tasks repository."""
from __future__ import annotations

import uuid

from . import db

_FIELDS = ("title", "description", "status", "priority")


def _row(r: dict) -> dict:
    return {k: r[k] for k in ("id", "title", "description", "status", "priority", "created_at", "updated_at")}


async def list_tasks() -> list[dict]:
    rows = await db.fetchall("SELECT * FROM task ORDER BY created_at DESC")
    return [_row(r) for r in rows]


async def create(data: dict) -> dict:
    tid = str(uuid.uuid4())
    ts = db.now()
    await db.execute(
        "INSERT INTO task(id, title, description, status, priority, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (tid, (data.get("title") or "New Task").strip(), data.get("description", ""),
         data.get("status", "todo"), data.get("priority", "medium"), ts, ts),
    )
    r = await db.fetchone("SELECT * FROM task WHERE id=?", (tid,))
    return _row(r)


async def update(task_id: str, data: dict) -> dict | None:
    existing = await db.fetchone("SELECT * FROM task WHERE id=?", (task_id,))
    if not existing:
        return None
    merged = {f: data.get(f, existing[f]) for f in _FIELDS}
    await db.execute(
        "UPDATE task SET title=?, description=?, status=?, priority=?, updated_at=? WHERE id=?",
        (merged["title"], merged["description"], merged["status"], merged["priority"], db.now(), task_id),
    )
    r = await db.fetchone("SELECT * FROM task WHERE id=?", (task_id,))
    return _row(r)


async def delete(task_id: str) -> bool:
    existing = await db.fetchone("SELECT id FROM task WHERE id=?", (task_id,))
    if not existing:
        return False
    await db.execute("DELETE FROM task WHERE id=?", (task_id,))
    return True
