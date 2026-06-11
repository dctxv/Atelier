"""Memory atom repository — single ingestion target with Living Memory v2 support.

An atom is a short piece of text plus its vector (in memory_vec) and its FTS
row (in memory_fts), all keyed by the atom's integer rowid. Writing all three
inside one serialized transaction keeps them consistent.

Living Memory v2 adds structured fields (subject, predicate, object, etc.) as
nullable columns so all legacy atoms (NULL subject/predicate) keep working
identically. Reconciliation happens in the extraction worker *before* calling
add_atom — this function is the write choke point only.
"""
from __future__ import annotations

import asyncio
import json
import uuid

from . import db, embeddings

DEDUP_THRESHOLD = 0.92
CORROB_STEP     = 0.3   # diminishing-returns corroboration step
CORROB_CAP      = 0.98  # max stored confidence from corroboration


def _row_to_atom(r: dict) -> dict:
    return {
        "id":                 r["id"],
        "text":               r["text"],
        "type":               r.get("type"),
        "salience":           r.get("salience"),
        "source_kind":        r.get("source_kind"),
        "source_id":          r.get("source_id"),
        "created_at":         r.get("created_at"),
        "last_used_at":       r.get("last_used_at"),
        "pinned":             bool(r.get("pinned")),
        "project_id":         r.get("project_id"),
        # Structured fields — NULL on legacy atoms
        "subject":            r.get("subject"),
        "predicate":          r.get("predicate"),
        "predicate_category": r.get("predicate_category"),
        "object":             r.get("object"),
        "polarity":           r.get("polarity"),
        "intensity":          r.get("intensity"),
        "modality":           r.get("modality"),
        "confidence":         r.get("confidence"),
        "valid_from":         r.get("valid_from"),
        "valid_until":        r.get("valid_until"),
        "temporal_raw":       r.get("temporal_raw"),
        "status":             r.get("status") or "active",
        "superseded_by":      r.get("superseded_by"),
        "meta":               json.loads(r["meta"]) if r.get("meta") else None,
    }


async def _nearest(vec: list[float]) -> tuple[str, float] | None:
    """Return (atom_id, cosine_similarity) of the closest active atom, if any."""
    rows = await db.fetchall(
        "SELECT m.id AS id, v.distance AS distance FROM "
        "(SELECT rowid, distance FROM memory_vec WHERE embedding MATCH ? ORDER BY distance LIMIT 1) v "
        "JOIN memory_atom m ON m.rowid = v.rowid "
        "WHERE (m.status='active' OR m.status IS NULL) "
        "ORDER BY v.distance",
        (db.serialize_f32(vec),),
    )
    if not rows:
        return None
    return rows[0]["id"], 1.0 - rows[0]["distance"]


async def log_event(atom_id: str, kind: str, detail: dict | None = None) -> None:
    """Append an entry to memory_event (best-effort, never raises)."""
    try:
        event_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO memory_event(id, atom_id, kind, detail, created_at) VALUES(?,?,?,?,?)",
            (event_id, atom_id, kind, json.dumps(detail) if detail else None, db.now()),
        )
    except Exception:
        pass


async def add_atom(
    text: str,
    type_: str = "fact",
    source_kind: str = "manual",
    source_id: str | None = None,
    salience: float = 1.0,
    pinned: bool = False,
    dedup: bool = False,
    project_id: str | None = None,
    # Living Memory v2 structured fields
    subject: str | None = None,
    predicate: str | None = None,
    predicate_category: str | None = None,
    object_val: str | None = None,
    polarity: float | None = None,
    intensity: float | None = None,
    modality: str | None = None,
    confidence: float | None = None,
    valid_from: int | None = None,
    valid_until: int | None = None,
    temporal_raw: str | None = None,
    meta: dict | None = None,
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
                await db.execute(
                    "UPDATE memory_atom SET salience=MIN(salience+0.1, 5.0), last_used_at=? WHERE id=?",
                    (db.now(), existing["id"]),
                )
                await db.bump_mutation_seq()
                await log_event(existing["id"], "corroborated", {"via": "dedup"})
                return await get_atom(existing["id"])

    atom_id = str(uuid.uuid4())
    ts = db.now()
    payload = db.serialize_f32(vec)
    meta_str = json.dumps(meta) if meta else None
    vf = valid_from or ts

    def op(conn):
        conn.execute(
            "INSERT INTO memory_atom("
            "id, text, type, salience, source_kind, source_id, "
            "created_at, last_used_at, pinned, project_id, "
            "subject, predicate, predicate_category, object, polarity, intensity, "
            "modality, confidence, valid_from, valid_until, temporal_raw, status, meta"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                atom_id, text, type_, salience, source_kind, source_id,
                ts, ts, int(pinned), project_id,
                subject, predicate, predicate_category, object_val,
                polarity, intensity, modality, confidence, vf, valid_until,
                temporal_raw, "active", meta_str,
            ),
        )
        rid = conn.execute("SELECT rowid FROM memory_atom WHERE id=?", (atom_id,)).fetchone()[0]
        conn.execute("INSERT INTO memory_vec(rowid, embedding) VALUES(?,?)", (rid, payload))
        conn.execute("INSERT INTO memory_fts(rowid, text) VALUES(?,?)", (rid, text))

    await db.write(op)
    await db.bump_mutation_seq()
    await log_event(atom_id, "created", {"source_kind": source_kind})

    from .retrieval import _ensure_knn_cache
    asyncio.create_task(_ensure_knn_cache())

    return await get_atom(atom_id)


async def get_atom(atom_id: str) -> dict | None:
    row = await db.fetchone("SELECT * FROM memory_atom WHERE id=?", (atom_id,))
    return _row_to_atom(row) if row else None


async def list_atoms(limit: int = 500, include_inactive: bool = False) -> list[dict]:
    if include_inactive:
        rows = await db.fetchall(
            "SELECT * FROM memory_atom ORDER BY pinned DESC, created_at DESC LIMIT ?",
            (limit,),
        )
    else:
        rows = await db.fetchall(
            "SELECT * FROM memory_atom WHERE (status='active' OR status IS NULL) "
            "ORDER BY pinned DESC, created_at DESC LIMIT ?",
            (limit,),
        )
    return [_row_to_atom(r) for r in rows]


async def update_atom(
    atom_id: str,
    *,
    text=None,
    type_=None,
    pinned=None,
    confidence=None,
    status=None,
    valid_until=None,
    superseded_by=None,
    meta=None,
) -> dict | None:
    existing = await db.fetchone("SELECT * FROM memory_atom WHERE id=?", (atom_id,))
    if not existing:
        return None

    new_text = text.strip() if isinstance(text, str) else existing["text"]
    vec = await embeddings.embed(new_text) if isinstance(text, str) else None
    payload = db.serialize_f32(vec) if vec is not None else None

    meta_val = existing.get("meta")
    if meta is not None:
        meta_val = json.dumps(meta)

    def op(conn):
        rid = conn.execute("SELECT rowid FROM memory_atom WHERE id=?", (atom_id,)).fetchone()[0]
        conn.execute(
            "UPDATE memory_atom SET "
            "text=?, type=?, pinned=?, confidence=?, status=?, valid_until=?, superseded_by=?, meta=? "
            "WHERE id=?",
            (
                new_text,
                type_ if type_ is not None else existing["type"],
                int(pinned) if pinned is not None else existing["pinned"],
                confidence if confidence is not None else existing.get("confidence"),
                status if status is not None else (existing.get("status") or "active"),
                valid_until if valid_until is not None else existing.get("valid_until"),
                superseded_by if superseded_by is not None else existing.get("superseded_by"),
                meta_val,
                atom_id,
            ),
        )
        if payload is not None:
            conn.execute("UPDATE memory_vec SET embedding=? WHERE rowid=?", (payload, rid))
            conn.execute("DELETE FROM memory_fts WHERE rowid=?", (rid,))
            conn.execute("INSERT INTO memory_fts(rowid, text) VALUES(?,?)", (rid, new_text))

    await db.write(op)
    await db.bump_mutation_seq()
    return await get_atom(atom_id)


async def set_pinned(atom_id: str, pinned: bool) -> bool:
    res = await db.fetchone("SELECT id FROM memory_atom WHERE id=?", (atom_id,))
    if not res:
        return False
    await db.execute("UPDATE memory_atom SET pinned=? WHERE id=?", (int(pinned), atom_id))
    await db.bump_mutation_seq()
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

    result = await db.write(op)
    if result:
        await db.bump_mutation_seq()
    return result or False


async def retract_atom(atom_id: str, reason: str = "user") -> bool:
    """Mark atom as retracted (confidence=0, excluded from retrieval). Logs event."""
    existing = await db.fetchone("SELECT id FROM memory_atom WHERE id=?", (atom_id,))
    if not existing:
        return False
    await db.execute(
        "UPDATE memory_atom SET status='retracted', confidence=0.0 WHERE id=?",
        (atom_id,),
    )
    await db.bump_mutation_seq()
    await log_event(atom_id, "retracted", {"reason": reason})
    return True


async def supersede_atom(old_id: str, new_id: str) -> bool:
    """Mark old atom as superseded by new_id. Logs event. Builds version chain."""
    existing = await db.fetchone("SELECT id FROM memory_atom WHERE id=?", (old_id,))
    if not existing:
        return False
    ts = db.now()
    await db.execute(
        "UPDATE memory_atom SET status='superseded', superseded_by=?, valid_until=? WHERE id=?",
        (new_id, ts, old_id),
    )
    await db.bump_mutation_seq()
    await log_event(old_id, "superseded", {"superseded_by": new_id})
    return True


async def corroborate_atom(atom_id: str) -> bool:
    """Apply corroboration boost: new = old + (0.98 − old) × 0.3, capped at 0.98."""
    existing = await db.fetchone("SELECT id, confidence FROM memory_atom WHERE id=?", (atom_id,))
    if not existing:
        return False
    old_conf = existing.get("confidence") or 0.9
    new_conf = min(CORROB_CAP, old_conf + (CORROB_CAP - old_conf) * CORROB_STEP)
    ts = db.now()
    await db.execute(
        "UPDATE memory_atom SET confidence=?, last_used_at=? WHERE id=?",
        (new_conf, ts, atom_id),
    )
    await db.bump_mutation_seq()
    await log_event(atom_id, "corroborated", {"old_conf": old_conf, "new_conf": new_conf})
    return True


async def count() -> int:
    row = await db.fetchone(
        "SELECT COUNT(*) AS n FROM memory_atom WHERE status='active' OR status IS NULL"
    )
    return row["n"] if row else 0
