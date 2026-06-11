"""Session + message HTTP layer (chat history persistence). Thin."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request

from services import sessions

router = APIRouter(prefix="/api")


@router.get("/sessions")
async def list_sessions(project_id: str | None = None, scope: str = "global"):
    """List sessions. ?project_id=<id> for a project's chats; otherwise
    scope='global' (default) returns unassigned chats, scope='all' returns every chat."""
    return {"sessions": await sessions.list_sessions(project_id=project_id, scope=scope)}


@router.post("/sessions")
async def create_session(request: Request):
    data = await request.json()
    project_id = data.get("project_id")
    s = await sessions.create(name=data.get("name", "New chat"),
                              model=data.get("model"), session_id=data.get("id"),
                              project_id=project_id)
    # Fire memory warming as a background task (Fix 4 / P1.4).
    # Never blocks the response — warming is a latency optimization only.
    try:
        from services.warming import warm_session
        asyncio.create_task(warm_session(s["id"], project_id))
    except Exception:
        pass
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
    kwargs = {"name": data.get("name"), "model": data.get("model")}
    # Only touch project_id when the key is present, so name/model edits don't
    # clobber it. Present-and-null = move the chat out to the main (global) tab;
    # present-and-id = move it into that project.
    if "project_id" in data:
        kwargs["project_id"] = data["project_id"]
    s = await sessions.update(session_id, **kwargs)
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
