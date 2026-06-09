"""Memory atom repository — the single ingestion target (Part 2.2).

An atom is a short piece of text plus its vector (in memory_vec) and its FTS
row (in memory_fts), all keyed by the atom's integer rowid. Writing all three
inside one serialized transaction keeps them consistent: there is never a vector
without its atom, or an FTS row pointing at a deleted atom.
"""
from __future__ import annotations

import asyncio
import uuid

from . import db, embeddings

DEDUP_THRESHOLD = 0.92  # cosine; above this we update an existing atom, not insert


def _row_to_atom(r: dict) -> dict:
    return {
        "id": r["id"],
        "text": r["text"],
        "type": r.get("type"),
        "salience": r.get("salience"),
        "source_kind": r.get("source_kind"),
        "source_id": r.get("source_id"),
        "created_at": r.get("created_at"),
        "last_used_at": r.get("last_used_at"),
        "pinned": bool(r.get("pinned")),
    }


async def _nearest(vec: list[float]) -> tuple[str, float] | None:
    """Return (atom_id, cosine_similarity) of the closest existing atom, if any."""
    rows = await db.fetchall(
        "SELECT m.id AS id, v.distance AS distance FROM "
        "(SELECT rowid, distance FROM memory_vec WHERE embedding MATCH ? ORDER BY distance LIMIT 1) v "
        "JOIN memory_atom m ON m.rowid = v.rowid ORDER BY v.distance",
        (db.serialize_f32(vec),),
    )
    if not rows:
        return None
    return rows[0]["id"], 1.0 - rows[0]["distance"]


async def add_atom(
    text: str,
    type_: str = "fact",
    source_kind: str = "manual",
    source_id: str | None = None,
    salience: float = 1.0,
    pinned: bool = False,
    dedup: bool = False,
    project_id: str | None = None,
) -> dict:
    text = (text or "").strip()
    if not text:
        raise ValueError("atom text required")

    vec = await embeddings.embed(text)

    if dedup:
        near = await _nearest(vec)
        if near and near[1] >= DEDUP_THRESHOLD:
            existing = await get_atom(near[0])
            if existing:
                # Refresh salience/recency rather than inserting a duplicate.
                await db.execute(
                    "UPDATE memory_atom SET salience=MIN(salience+0.1, 5.0), last_used_at=? WHERE id=?",
                    (db.now(), existing["id"]),
                )
                return await get_atom(existing["id"])

    atom_id = str(uuid.uuid4())
    ts = db.now()
    payload = db.serialize_f32(vec)

    def op(conn):
        conn.execute(
            "INSERT INTO memory_atom(id, text, type, salience, source_kind, source_id, "
            "created_at, last_used_at, pinned, project_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (atom_id, text, type_, salience, source_kind, source_id, ts, ts, int(pinned), project_id),
        )
        rid = conn.execute("SELECT rowid FROM memory_atom WHERE id=?", (atom_id,)).fetchone()[0]
        conn.execute("INSERT INTO memory_vec(rowid, embedding) VALUES(?,?)", (rid, payload))
        conn.execute("INSERT INTO memory_fts(rowid, text) VALUES(?,?)", (rid, text))

    await db.write(op)

    # Warm the numpy KNN cache in the background so the next retrieve() call
    # doesn't pay the full rebuild cost on the user-facing hot path.
    from .retrieval import _ensure_knn_cache  # local import avoids circular dep
    asyncio.create_task(_ensure_knn_cache())

    return await get_atom(atom_id)


async def get_atom(atom_id: str) -> dict | None:
    row = await db.fetchone("SELECT * FROM memory_atom WHERE id=?", (atom_id,))
    return _row_to_atom(row) if row else None


async def list_atoms(limit: int = 500) -> list[dict]:
    rows = await db.fetchall(
        "SELECT * FROM memory_atom ORDER BY pinned DESC, created_at DESC LIMIT ?", (limit,)
    )
    return [_row_to_atom(r) for r in rows]


async def update_atom(atom_id: str, *, text=None, type_=None, pinned=None) -> dict | None:
    existing = await db.fetchone("SELECT * FROM memory_atom WHERE id=?", (atom_id,))
    if not existing:
        return None

    new_text = text.strip() if isinstance(text, str) else existing["text"]
    vec = await embeddings.embed(new_text) if isinstance(text, str) else None
    payload = db.serialize_f32(vec) if vec is not None else None

    def op(conn):
        rid = conn.execute("SELECT rowid FROM memory_atom WHERE id=?", (atom_id,)).fetchone()[0]
        conn.execute(
            "UPDATE memory_atom SET text=?, type=?, pinned=? WHERE id=?",
            (
                new_text,
                type_ if type_ is not None else existing["type"],
                int(pinned) if pinned is not None else existing["pinned"],
                atom_id,
            ),
        )
        if payload is not None:
            conn.execute("UPDATE memory_vec SET embedding=? WHERE rowid=?", (payload, rid))
            conn.execute("DELETE FROM memory_fts WHERE rowid=?", (rid,))
            conn.execute("INSERT INTO memory_fts(rowid, text) VALUES(?,?)", (rid, new_text))

    await db.write(op)
    return await get_atom(atom_id)


async def set_pinned(atom_id: str, pinned: bool) -> bool:
    res = await db.fetchone("SELECT id FROM memory_atom WHERE id=?", (atom_id,))
    if not res:
        return False
    await db.execute("UPDATE memory_atom SET pinned=? WHERE id=?", (int(pinned), atom_id))
    return True


async def delete_atom(atom_id: str) -> bool:
    def op(conn):
        row = conn.execute("SELECT rowid FROM memory_atom WHERE id=?", (atom_id,)).fetchone()
        if not row:
            return False
        rid = row[0]
        conn.execute("DELETE FROM memory_atom WHERE id=?", (atom_id,))
        conn.execute("DELETE FROM memory_vec WHERE rowid=?", (rid,))
        conn.execute("DELETE FROM memory_fts WHERE rowid=?", (rid,))
        return True

    return await db.write(op)


async def count() -> int:
    row = await db.fetchone("SELECT COUNT(*) AS n FROM memory_atom")
    return row["n"] if row else 0
