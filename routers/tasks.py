"""Tasks CRUD. Timestamps returned as ISO strings for frontend compat."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from services import commitments, tasks

router = APIRouter(prefix="/api")


def _out(t: dict) -> dict:
    def iso(e):
        return datetime.fromtimestamp(e, timezone.utc).isoformat() if e else None
    return {**t, "created_at": iso(t["created_at"]), "updated_at": iso(t["updated_at"])}


def _out_commitment(c: dict) -> dict:
    def iso(e):
        return datetime.fromtimestamp(e, timezone.utc).isoformat() if e else None
    return {
        **c,
        "created_at": iso(c.get("created_at")),
        "updated_at": iso(c.get("updated_at")),
        "confirmed_at": iso(c.get("confirmed_at")),
        "rejected_at": iso(c.get("rejected_at")),
    }


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


@router.get("/commitments")
async def get_commitments(status: str = "proposed"):
    return {
        "commitments": [
            _out_commitment(c)
            for c in await commitments.list_commitments(status=status, limit=100)
        ]
    }


@router.post("/commitments/{commitment_id}/confirm")
async def confirm_commitment(commitment_id: str):
    c = await commitments.confirm(commitment_id)
    if not c:
        raise HTTPException(404, "Commitment not found or cannot be confirmed")
    return {"ok": True, "commitment": _out_commitment(c)}


@router.post("/commitments/{commitment_id}/reject")
async def reject_commitment(commitment_id: str):
    c = await commitments.reject(commitment_id)
    if not c:
        raise HTTPException(404, "Commitment not found or cannot be rejected")
    return {"ok": True, "commitment": _out_commitment(c)}
