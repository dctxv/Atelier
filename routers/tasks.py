"""Tasks CRUD. Timestamps returned as ISO strings for frontend compat."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from services import tasks

router = APIRouter(prefix="/api")


def _out(t: dict) -> dict:
    def iso(e):
        return datetime.fromtimestamp(e, timezone.utc).isoformat() if e else None
    return {**t, "created_at": iso(t["created_at"]), "updated_at": iso(t["updated_at"])}


@router.get("/tasks")
async def get_tasks():
    return {"tasks": [_out(t) for t in await tasks.list_tasks()]}


@router.post("/tasks")
async def create_task(request: Request):
    return {"ok": True, "task": _out(await tasks.create(await request.json()))}


@router.put("/tasks/{task_id}")
async def update_task(task_id: str, request: Request):
    t = await tasks.update(task_id, await request.json())
    if not t:
        raise HTTPException(404, "Task not found")
    return {"ok": True, "task": _out(t)}


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    if not await tasks.delete(task_id):
        raise HTTPException(404, "Task not found")
    return {"ok": True}
