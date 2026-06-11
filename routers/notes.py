"""Notes CRUD. Timestamps are returned as ISO strings for frontend compat
(the notes surface renders dates with `new Date(iso)`)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from services import notes
from workers import jobs

router = APIRouter(prefix="/api")


def _iso(epoch: int | None) -> str | None:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat() if epoch else None


def _out(n: dict) -> dict:
    return {**n, "created_at": _iso(n["created_at"]), "updated_at": _iso(n["updated_at"])}


@router.get("/notes")
async def get_notes():
    return {"notes": [_out(n) for n in await notes.list_notes()]}


@router.post("/notes")
async def create_note(request: Request):
    data = await request.json()
    note = await notes.create(data.get("title"), data.get("body", ""), bool(data.get("pinned", False)))
    return {"ok": True, "note": _out(note)}


@router.get("/notes/{note_id}")
async def get_note(note_id: str):
    note = await notes.get(note_id)
    if not note:
        raise HTTPException(404, "Note not found")
    return {"note": _out(note)}


@router.put("/notes/{note_id}")
async def update_note(note_id: str, request: Request):
    data = await request.json()
    note = await notes.update(
        note_id,
        title=data.get("title"),
        body=data.get("body"),
        pinned=data.get("pinned"),
    )
    if not note:
        raise HTTPException(404, "Note not found")
    return {"ok": True, "note": _out(note)}


@router.delete("/notes/{note_id}")
async def delete_note(note_id: str):
    if not await notes.delete(note_id):
        raise HTTPException(404, "Note not found")
    return {"ok": True}
