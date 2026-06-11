"""Notes repository. Saved notes also flow into memory ingestion (Phase 4).

source_kind / meta columns added for the weekly memory diff (P1.6): notes
with source_kind='memory_diff' are created by the weekly diff job and are
never re-ingested into memory atoms (ingest_note skips that kind).
"""
from __future__ import annotations

import json
import uuid

from . import db


def _row(r: dict) -> dict:
    return {
        "id": r["id"], "title": r["title"], "body": r["body"],
        "pinned": bool(r["pinned"]), "created_at": r["created_at"], "updated_at": r["updated_at"],
        "source_kind": r.get("source_kind"),
        "meta": json.loads(r["meta"]) if r.get("meta") else None,
    }


async def list_notes() -> list[dict]:
    rows = await db.fetchall("SELECT * FROM note ORDER BY pinned DESC, updated_at DESC")
    return [_row(r) for r in rows]


async def get(note_id: str) -> dict | None:
    r = await db.fetchone("SELECT * FROM note WHERE id=?", (note_id,))
    return _row(r) if r else None


async def create(
    title: str,
    body: str = "",
    pinned: bool = False,
    source_kind: str | None = None,
    meta: str | None = None,
) -> dict:
    nid = str(uuid.uuid4())
    ts = db.now()
    await db.execute(
        "INSERT INTO note(id, title, body, pinned, created_at, updated_at, source_kind, meta) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (nid, (title or "Untitled Note").strip(), body or "", int(pinned), ts, ts,
         source_kind, meta),
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


async def upsert_diff_note(week_start_iso: str, title: str, body: str) -> dict:
    """Upsert the weekly memory digest note. Idempotent by week_start_iso.

    Uses source_kind='memory_diff' so the extraction worker skips re-ingestion.
    """
    meta_val = json.dumps({"diff_week_start": week_start_iso})
    row = await db.fetchone(
        "SELECT id FROM note WHERE source_kind='memory_diff' AND meta=?",
        (meta_val,),
    )
    if row:
        note_id = row["id"]
        await db.execute(
            "UPDATE note SET title=?, body=?, updated_at=? WHERE id=?",
            (title, body, db.now(), note_id),
        )
        return await get(note_id)
    return await create(title, body, pinned=False, source_kind="memory_diff", meta=meta_val)
