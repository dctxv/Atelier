"""Memory CRUD + retrieval. Response shape stays compatible with the existing
frontend (category <- type, timestamp <- created_at)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from services import memory, retrieval

router = APIRouter(prefix="/api")


def _legacy(atom: dict) -> dict:
    return {
        "id": atom["id"],
        "text": atom["text"],
        "category": atom.get("type", "fact"),
        "timestamp": atom.get("created_at"),
        "pinned": bool(atom.get("pinned")),
        "source_kind": atom.get("source_kind"),
    }


@router.get("/memory")
async def get_memory():
    atoms = await memory.list_atoms()
    return {"memories": [_legacy(a) for a in atoms]}


@router.post("/memory")
async def add_memory(request: Request):
    data = await request.json()
    text = (data.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "Memory text required")
    atom = await memory.add_atom(
        text=text, type_=data.get("category", "fact"),
        source_kind="manual", pinned=bool(data.get("pinned", False)),
    )
    return {"ok": True, "memory": _legacy(atom)}


@router.put("/memory/{memory_id}")
async def update_memory(memory_id: str, request: Request):
    data = await request.json()
    atom = await memory.update_atom(
        memory_id,
        text=data.get("text"),
        type_=data.get("category"),
        pinned=data.get("pinned"),
    )
    if not atom:
        raise HTTPException(404, "Memory not found")
    return {"ok": True, "memory": _legacy(atom)}


@router.delete("/memory/{memory_id}")
async def delete_memory(memory_id: str):
    if not await memory.delete_atom(memory_id):
        raise HTTPException(404, "Memory not found")
    return {"ok": True}


@router.post("/memory/{memory_id}/pin")
async def pin_memory(memory_id: str, request: Request):
    data = await request.json()
    pinned = bool(data.get("pinned", True))
    if not await memory.set_pinned(memory_id, pinned):
        raise HTTPException(404, "Memory not found")
    return {"ok": True, "pinned": pinned}


@router.post("/memory/search")
async def search_memory(request: Request):
    data = await request.json()
    atoms = await retrieval.retrieve(
        (data.get("query") or "").strip(),
        k=int(data.get("k", 12)),
        budget_tokens=int(data.get("budget_tokens", 700)),
    )
    return {"results": atoms}
