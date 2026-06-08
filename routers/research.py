"""Research endpoints. Runs the deep-research pipeline as a background job.

The frontend reads a flat `raw_report` string and a `session_id`, so we render
the structured sections into markdown here while keeping the structured fields.

Phase 4 adds GET /research/{id}/stream — an SSE endpoint that replays buffered
progress events and then tails new ones until the job finishes or disconnects.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from services import config, db
from services import research as research_repo
from workers import jobs

router = APIRouter(prefix="/api")


def _render_report(item: dict) -> str:
    parts = []
    if item.get("summary"):
        parts.append(item["summary"])
    for sec in item.get("sections", []):
        title = sec.get("title", "")
        content = sec.get("content", "")
        parts.append(f"{title}\n\n{content}" if title else content)
    return "\n\n".join(p for p in parts if p).strip()


def _shape(item: dict) -> dict:
    return {
        **item,
        "session_id": item["id"],
        "raw_report": _render_report(item),
        "source_count": len(item.get("sources", [])),
    }


@router.get("/research")
async def list_research():
    rows = await research_repo.list_research()
    out = []
    for r in rows:
        sc = await db.fetchone(
            "SELECT COUNT(*) AS n FROM research_source WHERE research_id=?", (r["id"],)
        )
        out.append({**r, "session_id": r["id"], "source_count": sc["n"] if sc else 0})
    return {"research": out}


@router.post("/research/start")
async def start_research(request: Request):
    data = await request.json()
    query = (data.get("query") or "").strip()
    if not query:
        raise HTTPException(400, "Research query required")
    if not await config.active_endpoint_raw() or not await config.get_setting("active_model"):
        raise HTTPException(400, "Configure an endpoint and model in Chat first")
    item = await research_repo.create(query)
    await jobs.enqueue("research", {"research_id": item["id"]})
    return {"ok": True, "id": item["id"], "session_id": item["id"], "status": "running"}


@router.get("/research/{research_id}/stream")
async def stream_research_progress(research_id: str):
    """SSE stream of progress events for a running research job.

    Events: planning | round | sources_found | synthesizing | section_ready |
            claim_verified | done | error | heartbeat

    If the job has already finished, emits a single done/error event and closes.
    Replays all buffered events from the start, so reconnects are safe.
    """
    from workers.research import get_store

    # If the job is already finished, emit a synthetic terminal event.
    item = await research_repo.get(research_id)
    if item and item.get("status") in ("done", "error"):
        ev = json.dumps({"phase": item["status"]})

        async def quick():
            yield f"data: {ev}\n\n"

        return StreamingResponse(
            quick(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    store = get_store(research_id)

    async def event_gen():
        async for ev in store.stream():
            yield f"data: {json.dumps(ev)}\n\n"

    return StreamingResponse(
        event_gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                 "Connection": "keep-alive"},
    )


@router.get("/research/{research_id}")
async def get_research(research_id: str):
    item = await research_repo.get(research_id)
    if not item:
        raise HTTPException(404, "Research not found")
    return {"research": _shape(item)}


@router.delete("/research/{research_id}")
async def delete_research(research_id: str):
    if not await research_repo.delete(research_id):
        raise HTTPException(404, "Research not found")
    return {"ok": True}
