"""Notes repository. Saved notes also flow into memory ingestion (Phase 4)."""
from __future__ import annotations

import uuid

from . import db


def _row(r: dict) -> dict:
    return {
        "id": r["id"], "title": r["title"], "body": r["body"],
        "pinned": bool(r["pinned"]), "created_at": r["created_at"], "updated_at": r["updated_at"],
    }


async def list_notes() -> list[dict]:
    rows = await db.fetchall("SELECT * FROM note ORDER BY pinned DESC, updated_at DESC")
    return [_row(r) for r in rows]


async def get(note_id: str) -> dict | None:
    r = await db.fetchone("SELECT * FROM note WHERE id=?", (note_id,))
    return _row(r) if r else None


async def create(title: str, body: str = "", pinned: bool = False) -> dict:
    nid = str(uuid.uuid4())
    ts = db.now()
    await db.execute(
        "INSERT INTO note(id, title, body, pinned, created_at, updated_at) VALUES(?,?,?,?,?,?)",
        (nid, (title or "Untitled Note").strip(), body or "", int(pinned), ts, ts),
    )
    return await get(nid)


async def update(note_id: str, *, title=None, body=None, pinned=None) -> dict | None:
    existing = await db.fetchone("SELECT * FROM note WHERE id=?", (note_id,))
    if not existing:
        return None
    await db.execute(
        "UPDATE note SET title=?, body=?, pinned=?, updated_at=? WHERE id=?",
        (
            (title or "Untitled Note").strip() if title is not None else existing["title"],
            body if body is not None else existing["body"],
            int(pinned) if pinned is not None else existing["pinned"],
            db.now(), note_id,
        ),
    )
    return await get(note_id)


async def delete(note_id: str) -> bool:
    existing = await db.fetchone("SELECT id FROM note WHERE id=?", (note_id,))
    if not existing:
        return False
    await db.execute("DELETE FROM note WHERE id=?", (note_id,))
    return True
