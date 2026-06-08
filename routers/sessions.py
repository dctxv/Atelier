"""Session + message HTTP layer (chat history persistence). Thin."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from services import sessions

router = APIRouter(prefix="/api")


@router.get("/sessions")
async def list_sessions():
    return {"sessions": await sessions.list_sessions()}


@router.post("/sessions")
async def create_session(request: Request):
    data = await request.json()
    s = await sessions.create(name=data.get("name", "New chat"),
                              model=data.get("model"), session_id=data.get("id"))
    return {"ok": True, "session": s}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    s = await sessions.get_session(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    return {"session": s}


@router.patch("/sessions/{session_id}")
async def update_session(session_id: str, request: Request):
    data = await request.json()
    s = await sessions.update(session_id, name=data.get("name"), model=data.get("model"))
    if not s:
        raise HTTPException(404, "Session not found")
    return {"ok": True, "session": s}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    if not await sessions.delete(session_id):
        raise HTTPException(404, "Session not found")
    return {"ok": True}


@router.post("/sessions/import")
async def import_sessions(request: Request):
    data = await request.json()
    n = await sessions.import_sessions(data.get("sessions", []))
    return {"ok": True, "imported": n}
