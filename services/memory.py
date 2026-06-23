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

from . import config, db, embeddings

DEDUP_THRESHOLD = 0.92
CORROB_STEP     = 0.3   # diminishing-returns corroboration step
CORROB_CAP      = 0.98  # max stored confidence from corroboration

# ── W2: inferential memory ────────────────────────────────────────────────────
# A *derived* atom is a distinct class: modality='insight', type='inference',
# minted at status='proposed' so it is INVISIBLE to retrieval (Visibility Law —
# an inference is not "believed" until the user has seen and confirmed it). Its
# provenance (the source atoms it was inferred from) lives in meta.source_atom_ids
# so deleting the derived atom never touches the underlying stated facts.
INFERENCE_BASE_CONFIDENCE = 0.5   # lower than stated facts by default [VALIDATE]
INFERENCE_DEDUP_THRESHOLD = 0.90  # similarity above which an inference is a dup [VALIDATE]
INFERENCE_CORROB_STEP     = 0.34  # how fast a re-sighted inference gains confidence [VALIDATE]
INFERENCE_CORROB_CAP      = 0.90  # an inference never reaches stated-fact certainty [VALIDATE]


async def _cfg_float(key: str, default: float) -> float:
    val = await config.get_setting(key)
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


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
        "strand_id":          r.get("strand_id"),
        "strand_assigned_at": r.get("strand_assigned_at"),
        "cluster_dirty":      bool(r.get("cluster_dirty", 0)),
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
    status: str = "active",
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
            "modality, confidence, valid_from, valid_until, temporal_raw, status, meta, "
            "cluster_dirty"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                atom_id, text, type_, salience, source_kind, source_id,
                ts, ts, int(pinned), project_id,
                subject, predicate, predicate_category, object_val,
                polarity, intensity, modality, confidence, vf, valid_until,
                temporal_raw, status, meta_str, 1,
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
        membership_changed = isinstance(text, str) or status is not None
        conn.execute(
            "UPDATE memory_atom SET "
            "text=?, type=?, pinned=?, confidence=?, status=?, valid_until=?, superseded_by=?, meta=?, "
            "cluster_dirty=CASE WHEN ? THEN 1 ELSE cluster_dirty END "
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
                int(membership_changed),
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
        "UPDATE memory_atom SET status='retracted', confidence=0.0, cluster_dirty=1 WHERE id=?",
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
        "UPDATE memory_atom SET status='superseded', superseded_by=?, valid_until=?, cluster_dirty=1 WHERE id=?",
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


# ── W2: inferential memory — derived atoms with provenance ────────────────────

async def _existing_inference(text: str, subject, predicate, object_val,
                              vec: list[float]) -> str | None:
    """Idempotency: return the id of an existing insight atom that already says
    this (same subject/predicate/object, or vector-similar), else None. Re-running
    the inference pass must not spawn duplicate inferences."""
    if subject and predicate:
        rows = await db.fetchall(
            "SELECT id FROM memory_atom WHERE modality='insight' "
            "AND status IN ('proposed','active') "
            "AND subject=? AND predicate=? "
            "AND (object IS ? OR LOWER(object)=LOWER(?)) LIMIT 1",
            (subject, predicate, object_val, object_val or ""),
        )
        if rows:
            return rows[0]["id"]
    # Vector-similarity fallback over insight atoms only.
    rows = await db.fetchall(
        "SELECT m.id AS id, v.distance AS distance FROM "
        "(SELECT rowid, distance FROM memory_vec WHERE embedding MATCH ? ORDER BY distance LIMIT 5) v "
        "JOIN memory_atom m ON m.rowid = v.rowid "
        "WHERE m.modality='insight' AND m.status IN ('proposed','active') "
        "ORDER BY v.distance LIMIT 1",
        (db.serialize_f32(vec),),
    )
    threshold = await _cfg_float("intake.inference_novelty_threshold", 0.85)
    if rows and (1.0 - rows[0]["distance"]) >= threshold:
        return rows[0]["id"]
    return None


async def add_inference(
    text: str,
    source_atom_ids: list[str],
    kind: str = "pattern",
    subject: str | None = None,
    predicate: str | None = None,
    object_val: str | None = None,
    confidence: float | None = None,
    project_id: str | None = None,
    allow_new: bool = True,
) -> dict | None:
    """Mint a *derived* atom (Visibility Law: status='proposed', invisible to
    retrieval until confirmed). Provenance is the list of source atom ids it was
    inferred from. Idempotent: returns the existing inference if one already
    asserts the same thing, without creating a duplicate.

    Returns the atom dict, or None if `text` was empty.
    """
    text = (text or "").strip()
    if not text:
        return None
    subject   = (subject or "").lower().strip() or None
    predicate = (predicate or "").lower().strip() or None
    base_conf = await _cfg_float("intake.inference_base_confidence", INFERENCE_BASE_CONFIDENCE)
    conf = base_conf if confidence is None else max(0.05, min(0.9, confidence))

    vec = await embeddings.embed(text)
    dup_id = await _existing_inference(text, subject, predicate, object_val, vec)
    if dup_id:
        # Ex1/Ex6: a second sighting CORROBORATES — it raises confidence toward
        # (but never to) stated-fact certainty, boosts salience, and merges the
        # new evidence into provenance. Re-running stays idempotent (no new row).
        return await _corroborate_inference(dup_id, list(source_atom_ids or []))
    if not allow_new:
        return None

    meta = {
        "inference": True,
        "inference_kind": kind,
        "source_atom_ids": list(source_atom_ids or []),
    }
    atom = await add_atom(
        text=text,
        type_="inference",
        source_kind="inference",
        salience=0.6,
        dedup=False,                 # inference dedup is handled above, not vs facts
        project_id=project_id,
        subject=subject,
        predicate=predicate,
        object_val=object_val,
        modality="insight",
        confidence=conf,
        meta=meta,
        status="proposed",           # ← unbelieved until reviewed
    )
    await log_event(atom["id"], "inference_proposed",
                    {"kind": kind, "sources": list(source_atom_ids or [])})
    return atom


async def _corroborate_inference(atom_id: str, new_sources: list[str]) -> dict | None:
    """Second-sighting corroboration: raise an inference's confidence toward the
    cap, bump salience, and union the new evidence into its provenance."""
    existing = await get_atom(atom_id)
    if not existing:
        return None
    base_conf = await _cfg_float("intake.inference_base_confidence", INFERENCE_BASE_CONFIDENCE)
    step = await _cfg_float("intake.inference_corroboration_step", INFERENCE_CORROB_STEP)
    cap = await _cfg_float("intake.inference_corroboration_cap", INFERENCE_CORROB_CAP)
    old_conf = existing.get("confidence") or base_conf
    new_conf = min(cap, old_conf + (cap - old_conf) * step)
    new_sal = min(5.0, (existing.get("salience") or 0.6) + 0.2)
    meta = existing.get("meta") or {}
    merged = list(dict.fromkeys((meta.get("source_atom_ids") or []) + (new_sources or [])))
    meta["source_atom_ids"] = merged
    meta["sightings"] = int(meta.get("sightings", 1)) + 1
    await db.execute(
        "UPDATE memory_atom SET confidence=?, salience=?, last_used_at=?, meta=? WHERE id=?",
        (new_conf, new_sal, db.now(), json.dumps(meta), atom_id),
    )
    await db.bump_mutation_seq()
    await log_event(atom_id, "inference_corroborated",
                    {"old_conf": old_conf, "new_conf": new_conf,
                     "sightings": meta["sightings"]})
    return await get_atom(atom_id)


async def distinct_source_count(atom_ids: list[str]) -> int:
    """Count distinct provenance sources for evidence gating.

    Chat atoms use their session/source id as the unit; atoms without a stable
    source id count individually so manual fixtures can still exercise the gate.
    """
    ids = sorted({aid for aid in (atom_ids or []) if aid})
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    rows = await db.fetchall(
        f"SELECT id, source_kind, source_id FROM memory_atom WHERE id IN ({placeholders})",
        tuple(ids),
    )
    sources: set[tuple[str, str]] = set()
    for row in rows:
        kind = row.get("source_kind") or "unknown"
        source_id = row.get("source_id")
        if source_id:
            sources.add((kind, source_id))
        else:
            sources.add((kind, row["id"]))
    return len(sources)


async def retire_atom(atom_id: str, reason: str = "pruned") -> bool:
    """Soft-retire an atom without deleting its row, vector, or audit history."""
    existing = await db.fetchone("SELECT id FROM memory_atom WHERE id=?", (atom_id,))
    if not existing:
        return False
    await db.execute(
        "UPDATE memory_atom SET status='retired', cluster_dirty=1 WHERE id=?",
        (atom_id,),
    )
    await db.bump_mutation_seq()
    await log_event(atom_id, "retired", {"reason": reason})
    return True


async def confirm_inference(atom_id: str) -> bool:
    """Promote a proposed inference to believed (status='active'). It keeps its
    insight modality (and the (inferred) tag) — it is now a shown-and-confirmed
    inference, distinct from a directly-stated fact."""
    row = await db.fetchone("SELECT id, status FROM memory_atom WHERE id=?", (atom_id,))
    if not row:
        return False
    await db.execute("UPDATE memory_atom SET status='active', cluster_dirty=1 WHERE id=?", (atom_id,))
    await db.bump_mutation_seq()
    await log_event(atom_id, "inference_confirmed", None)
    from .retrieval import _ensure_knn_cache
    asyncio.create_task(_ensure_knn_cache())
    return True


async def reject_inference(atom_id: str) -> bool:
    """Reject a proposed inference. It is suppressed (status='rejected',
    confidence 0) — kept for audit and as signal to tighten future inference."""
    row = await db.fetchone("SELECT id FROM memory_atom WHERE id=?", (atom_id,))
    if not row:
        return False
    await db.execute(
        "UPDATE memory_atom SET status='rejected', confidence=0.0, cluster_dirty=1 WHERE id=?", (atom_id,)
    )
    await db.bump_mutation_seq()
    await log_event(atom_id, "inference_rejected", None)
    return True


async def list_inferences(status: str = "proposed", limit: int = 100) -> list[dict]:
    """Inferences at a given lifecycle status, each with resolved provenance."""
    rows = await db.fetchall(
        "SELECT * FROM memory_atom WHERE modality='insight' AND status=? "
        "ORDER BY created_at DESC LIMIT ?",
        (status, limit),
    )
    out: list[dict] = []
    for r in rows:
        a = _row_to_atom(r)
        meta = a.get("meta") or {}
        a["inference_kind"] = meta.get("inference_kind", "inferred")
        a["source_atom_ids"] = meta.get("source_atom_ids", [])
        a["provenance"] = await provenance(a["id"])
        out.append(a)
    return out


async def provenance(atom_id: str) -> list[dict]:
    """Resolve the source atoms a derived atom was inferred from. Missing/deleted
    sources are simply omitted (deletability never breaks the derived atom)."""
    atom = await get_atom(atom_id)
    if not atom:
        return []
    meta = atom.get("meta") or {}
    ids = meta.get("source_atom_ids") or []
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    rows = await db.fetchall(
        f"SELECT id, text, modality, confidence, created_at FROM memory_atom "
        f"WHERE id IN ({placeholders})", tuple(ids),
    )
    by_id = {r["id"]: r for r in rows}
    return [
        {"id": i, "text": by_id[i]["text"], "modality": by_id[i].get("modality"),
         "confidence": by_id[i].get("confidence"), "created_at": by_id[i].get("created_at")}
        for i in ids if i in by_id
    ]


# ── W6: extraction visibility & steering ──────────────────────────────────────
# What the system learned from conversations, made visible and correctable. A
# stated fact is believed immediately (extraction is trusted) but stays in the
# review queue until the user accepts it; rejecting it is *signal* — the triple is
# remembered so extraction won't silently re-learn it.

_SUPPRESS_KEY = "memory.extraction_suppressions"
_SUPPRESS_MAX = 300


def _triple_key(subject, predicate, object_val) -> str | None:
    s = (subject or "").lower().strip()
    p = (predicate or "").lower().strip()
    if not s or not p:
        return None
    o = (object_val or "").lower().strip()
    return f"{s}\x01{p}\x01{o}"


async def list_unreviewed_facts(limit: int = 50) -> list[dict]:
    """Recent extraction output (stated facts) the user hasn't reviewed yet."""
    rows = await db.fetchall(
        "SELECT * FROM memory_atom "
        "WHERE source_kind='chat' AND (status='active' OR status IS NULL) "
        "AND (modality IS NULL OR modality NOT IN ('insight','hypothesis')) "
        "ORDER BY created_at DESC LIMIT 400",
    )
    out: list[dict] = []
    for r in rows:
        a = _row_to_atom(r)
        if (a.get("meta") or {}).get("reviewed"):
            continue
        out.append(a)
        if len(out) >= limit:
            break
    return out


async def mark_reviewed(atom_id: str) -> bool:
    """Accept an extracted fact: dismiss it from the review queue (keep believed)."""
    existing = await get_atom(atom_id)
    if not existing:
        return False
    meta = existing.get("meta") or {}
    meta["reviewed"] = True
    await db.execute(
        "UPDATE memory_atom SET meta=? WHERE id=?", (json.dumps(meta), atom_id)
    )
    await db.bump_mutation_seq()
    await log_event(atom_id, "reviewed", {"action": "accepted"})
    return True


async def add_rejection_signal(atom: dict) -> None:
    """Record a rejected triple so extraction won't silently re-learn it (W6 →
    feeds the gate). Best-effort, capped, deduped."""
    key = _triple_key(atom.get("subject"), atom.get("predicate"), atom.get("object"))
    if not key:
        return
    raw = await db.fetchone("SELECT value FROM app_config WHERE key=?", (_SUPPRESS_KEY,))
    try:
        lst = json.loads(raw["value"]) if raw and raw.get("value") else []
    except Exception:
        lst = []
    if key in lst:
        return
    lst.append(key)
    if len(lst) > _SUPPRESS_MAX:
        lst = lst[-_SUPPRESS_MAX:]
    await db.execute(
        "INSERT INTO app_config(key, value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (_SUPPRESS_KEY, json.dumps(lst)),
    )


async def is_extraction_suppressed(subject, predicate, object_val) -> bool:
    """True when a triple was previously rejected by the user (W6 steering)."""
    key = _triple_key(subject, predicate, object_val)
    if not key:
        return False
    raw = await db.fetchone("SELECT value FROM app_config WHERE key=?", (_SUPPRESS_KEY,))
    try:
        lst = json.loads(raw["value"]) if raw and raw.get("value") else []
    except Exception:
        return False
    return key in lst


async def surface_contradiction(atom_ids: list[str], prompt_text: str,
                                kind: str = "contradiction") -> str | None:
    """Surface a detected conflict for the user to reconcile (do NOT auto-resolve).

    kind='contradiction' is a logical conflict (Sydney vs Melbourne);
    kind='tension' is a tradeoff to make visible, not resolve (the motivating
    work that also carries a health cost — Ex6). Idempotent: if an open question
    already covers this atom set, returns None.
    """
    atom_ids = sorted(set(atom_ids or []))
    if len(atom_ids) < 2:
        return None
    key = json.dumps(atom_ids)
    existing = await db.fetchone(
        "SELECT id FROM memory_question WHERE kind IN ('contradiction','tension') "
        "AND status='open' AND atom_ids=?", (key,),
    )
    if existing:
        return None
    qid = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO memory_question(id, kind, atom_ids, prompt_text, status, created_at) "
        "VALUES(?,?,?,?,?,?)",
        (qid, kind if kind in ("contradiction", "tension") else "contradiction",
         key, prompt_text, "open", db.now()),
    )
    return qid
