"""Memory warming (P1.4) — composite session pre-fetch.

Warming Law (revised — this is the accurate statement):
  Warming may serve a predicted retrieval block when the first message falls
  within cos >= memory.warm_discard_cos of the predicted trajectory, the
  stash is fresh, and memory_mutation_seq is unchanged.  The guarantee is
  byte-identity to a cold computation of the predicted query at warm time —
  not content-invariance with this exact first message, because the blend
  query and the first message are different queries.  G4(a) tests cache
  fidelity, not content-invariance.

Explicitly absent: any emotional/affect signal.  The previous-session
centroid is the legitimate kernel of "recent trajectory".  Do not add
mood inference here.

All weights are app_config knobs [VALIDATE] — never hardcoded constants.
"""
from __future__ import annotations

import asyncio
import json
import time as _time
from collections import OrderedDict

import numpy as np

from . import config, db, embeddings, retrieval

# In-process stash — keyed by session_id, OrderedDict for LRU eviction.
_stash: OrderedDict[str, dict] = OrderedDict()
_STASH_CAP = 32


async def _get_cfg(key: str, default):
    val = await config.get_setting(key)
    if val is None:
        return default
    try:
        return type(default)(val)
    except Exception:
        return default


async def _current_mutation_seq() -> int:
    row = await db.fetchone("SELECT value FROM app_config WHERE key='memory_mutation_seq'")
    return int(row["value"]) if row else 0


async def _blend_query_vec(session_id: str, project_id: str | None) -> bytes | None:
    """Build the composite query vector from weighted components.

    Returns serialized float32 bytes, or None if not enough data.
    """
    weights_raw = await config.get_setting("memory.warm_weights")
    weights: dict[str, float]
    if weights_raw:
        try:
            weights = json.loads(weights_raw)
        except Exception:
            weights = {}
    else:
        weights = {}
    if not weights:
        weights = {"prev": 0.35, "goals": 0.20, "commits": 0.15, "slots": 0.15, "manifest": 0.15}

    components: list[tuple[np.ndarray, float]] = []

    # 1. Previous-session centroid (last session's user messages, max 10)
    try:
        prev_sessions = await db.fetchall(
            "SELECT id FROM session ORDER BY created_at DESC LIMIT 5"
        )
        prev_id: str | None = None
        for sess in prev_sessions:
            if sess["id"] != session_id:
                prev_id = sess["id"]
                break
        if prev_id:
            msgs = await db.fetchall(
                "SELECT content FROM message WHERE session_id=? AND role='user' "
                "ORDER BY created_at DESC LIMIT 10",
                (prev_id,),
            )
            if msgs:
                vecs = []
                for m in msgs:
                    if m.get("content"):
                        vecs.append(await embeddings.embed(m["content"]))
                if vecs:
                    mat = np.array(vecs, dtype=np.float32)
                    centroid = mat.mean(axis=0)
                    components.append((centroid, weights.get("prev", 0.35)))
    except Exception:
        pass

    # 2. Open goals touched <= 14 days
    try:
        cutoff = db.now() - 14 * 86400
        goals = await db.fetchall(
            "SELECT text FROM memory_atom "
            "WHERE modality IN ('desire','plan') AND (status='active' OR status IS NULL) "
            "AND last_used_at >= ? LIMIT 5",
            (cutoff,),
        )
        if goals:
            vecs = []
            for g in goals:
                if g.get("text"):
                    vecs.append(await embeddings.embed(g["text"]))
            if vecs:
                mat = np.array(vecs, dtype=np.float32)
                centroid = mat.mean(axis=0)
                components.append((centroid, weights.get("goals", 0.20)))
    except Exception:
        pass

    # 3. Due / overdue commitments. Only confirmed commitments shape warming;
    # proposals are review-gated and must not influence retrieval/context.
    try:
        commits = await db.fetchall(
            "SELECT c.title FROM commitment c "
            "LEFT JOIN task t ON t.id=c.task_id "
            "WHERE c.status='active' AND (t.status IS NULL OR t.status='todo') "
            "ORDER BY c.created_at ASC LIMIT 5"
        )
        if len(commits) < 5:
            legacy = await db.fetchall(
                "SELECT title FROM task WHERE source_kind='assistant_commitment' "
                "AND status='todo' ORDER BY created_at ASC LIMIT ?",
                (5 - len(commits),),
            )
            commits.extend(legacy)
        if commits:
            vecs = []
            for c in commits:
                if c.get("title"):
                    vecs.append(await embeddings.embed(c["title"]))
            if vecs:
                mat = np.array(vecs, dtype=np.float32)
                centroid = mat.mean(axis=0)
                components.append((centroid, weights.get("commits", 0.15)))
    except Exception:
        pass

    # 4. Slot pattern vector (weekday × 4h block) when count >= 4 [VALIDATE]
    try:
        import datetime
        now_dt = datetime.datetime.utcnow()
        slot = f"{now_dt.weekday()}_{now_dt.hour // 4}"
        slot_row = await db.fetchone(
            "SELECT query_vec, count FROM memory_pattern WHERE slot=?", (slot,)
        )
        if slot_row and (slot_row.get("count") or 0) >= 4 and slot_row.get("query_vec"):
            slot_vec = np.frombuffer(bytes(slot_row["query_vec"]), dtype=np.float32)
            if len(slot_vec) == retrieval.DIM:
                components.append((slot_vec.copy(), weights.get("slots", 0.15)))
    except Exception:
        pass

    # 5. Project manifest centroid (only when project-scoped)
    if project_id:
        try:
            from . import projects as projects_svc
            proj = await projects_svc.get(project_id)
            if proj and proj.get("description"):
                vec = await embeddings.embed(proj["description"])
                components.append((np.array(vec, dtype=np.float32), weights.get("manifest", 0.15)))
        except Exception:
            pass

    if not components:
        return None

    # Renormalize weights to sum to 1
    total_w = sum(w for _, w in components)
    blend = np.zeros(retrieval.DIM, dtype=np.float32)
    for vec, w in components:
        if len(vec) == retrieval.DIM:
            blend += vec * (w / total_w)

    n = np.linalg.norm(blend)
    if n > 0:
        blend = blend / n

    return db.serialize_f32(blend.tolist())


async def _retrieve_with_vec(
    serialized_vec: bytes,
    budget: int,
    project_id: str | None,
) -> list[dict]:
    """Run retrieval using a pre-serialized query vector, bypassing embed()."""
    k = 12
    doc_k = retrieval.DOC_MAX_CHUNKS

    numpy_ids_raw, doc_vec_ids, pinned, ready_rows = await asyncio.gather(
        retrieval._numpy_knn(serialized_vec, k, project_id=project_id),
        retrieval._doc_vector_hits(serialized_vec, doc_k, project_id=project_id),
        db.fetchall("SELECT * FROM memory_atom WHERE pinned=1 ORDER BY created_at DESC"),
        db.fetchall("SELECT id FROM document WHERE status='ready'"),
    )

    pinned_ids = {p["id"] for p in pinned}
    if project_id is not None:
        project_atom_rows = await db.fetchall(
            "SELECT id FROM memory_atom WHERE project_id=?", (project_id,)
        )
        project_atom_ids = {r["id"] for r in project_atom_rows}
        allowed_ids = project_atom_ids | pinned_ids
        numpy_ids = [aid for aid in numpy_ids_raw if aid in allowed_ids][:k]
    else:
        project_only_rows = await db.fetchall(
            "SELECT id FROM memory_atom WHERE project_id IS NOT NULL AND project_id != ''"
        )
        project_only_ids = {r["id"] for r in project_only_rows}
        numpy_ids = [aid for aid in numpy_ids_raw if aid not in project_only_ids][:k]

    ready_doc_ids = {r["id"] for r in ready_rows}
    mem_scores = retrieval._rrf([numpy_ids])
    doc_scores = retrieval._rrf([doc_vec_ids]) if ready_doc_ids else {}
    mem_candidate_ids = set(mem_scores) | pinned_ids

    mem_rows: dict[str, dict] = {}
    if mem_candidate_ids:
        placeholders = ",".join("?" * len(mem_candidate_ids))
        rows = await db.fetchall(
            f"SELECT * FROM memory_atom WHERE id IN ({placeholders})", tuple(mem_candidate_ids)
        )
        mem_rows = {r["id"]: r for r in rows}

    now_ts = db.now()
    mem_rows = {
        k: v for k, v in mem_rows.items()
        if v.get("pinned") or retrieval._effective_confidence(v, now_ts) >= retrieval.FADING_THRESHOLD
    }
    mem_rows = {
        k: v for k, v in mem_rows.items()
        if v.get("predicate") != "suppressed" and v.get("modality") != "hypothesis"
    }

    import json as _json

    def _score(r: dict) -> float:
        base = mem_scores.get(r["id"], 0.0)
        if r["id"] in pinned_ids:
            base += 1.0
        return (base + retrieval._recency_boost(r.get("created_at"))) * retrieval._effective_confidence(r, now_ts)

    all_items = sorted([
        {
            "id": r["id"], "text": r["text"], "type": r.get("type"),
            "source_kind": r.get("source_kind"), "source_id": r.get("source_id"),
            "created_at": r.get("created_at"), "pinned": bool(r.get("pinned")),
            "score": round(_score(r), 4), "source_type": "memory",
            "modality": r.get("modality"), "predicate": r.get("predicate"),
            "subject": r.get("subject"), "predicate_category": r.get("predicate_category"),
            "valid_from": r.get("valid_from"),
            "meta": _json.loads(r["meta"]) if r.get("meta") else None,
        }
        for r in mem_rows.values()
    ], key=lambda x: x["score"], reverse=True)

    out, used = [], 0
    for item in all_items:
        cost = retrieval._estimate_tokens(item["text"])
        if used + cost > budget and out:
            break
        out.append(item)
        used += cost
    return out


async def warm_session(session_id: str, project_id: str | None = None) -> None:
    """Background task: pre-fetch retrieval block for predicted first-turn query.

    Fires after POST /api/sessions.  Never blocks the session creation response.
    """
    try:
        budget = int(await _get_cfg("chat.memory_block_budget", 700))
        ttl = int(await _get_cfg("memory.warm_ttl_s", 600))
        mutation_seq = await _current_mutation_seq()

        query_vec_bytes = await _blend_query_vec(session_id, project_id)
        if not query_vec_bytes:
            return

        atoms = await _retrieve_with_vec(query_vec_bytes, budget, project_id)
        block = retrieval.format_block(atoms)

        if len(_stash) >= _STASH_CAP:
            _stash.popitem(last=False)
        _stash[session_id] = {
            "block": block,
            "query_vec": query_vec_bytes,
            "created_at": int(_time.time()),
            "mutation_seq": mutation_seq,
            "ttl": ttl,
        }
    except Exception:
        pass  # warming is best-effort — never crash session creation


async def pop_warm_block(
    session_id: str,
    first_msg_embedding: list[float],
    current_mutation_seq: int,
) -> str | None:
    """Return warm block if valid; always evict the stash entry.

    Returns None → caller runs cold retrieve (never a correctness issue).
    """
    stash = _stash.pop(session_id, None)
    if not stash:
        return None

    # TTL check
    age = int(_time.time()) - stash["created_at"]
    if age > stash.get("ttl", 600):
        return None

    # Mutation guard
    if stash["mutation_seq"] != current_mutation_seq:
        return None

    # Cosine gate [VALIDATE]
    try:
        warm_cos_raw = await config.get_setting("memory.warm_discard_cos")
        warm_cos = float(warm_cos_raw) if warm_cos_raw else 0.30

        q = np.array(first_msg_embedding, dtype=np.float32)
        w = np.frombuffer(stash["query_vec"], dtype=np.float32)
        qn, wn = np.linalg.norm(q), np.linalg.norm(w)
        if qn > 0 and wn > 0:
            cos = float(np.dot(q / qn, w / wn))
        else:
            cos = 0.0
        if cos < warm_cos:
            return None
    except Exception:
        return None

    return stash["block"]


async def update_slot_pattern(session_id: str, user_message: str) -> None:
    """Update the slot's EWMA query vector after a turn (P1.4 §5.3)."""
    try:
        import datetime
        now_dt = datetime.datetime.utcnow()
        slot = f"{now_dt.weekday()}_{now_dt.hour // 4}"

        vec = await embeddings.embed(user_message)
        vec_arr = np.array(vec, dtype=np.float32)
        n = np.linalg.norm(vec_arr)
        if n > 0:
            vec_arr = vec_arr / n

        row = await db.fetchone(
            "SELECT query_vec, count FROM memory_pattern WHERE slot=?", (slot,)
        )
        if row and row.get("query_vec"):
            old = np.frombuffer(bytes(row["query_vec"]), dtype=np.float32)
            if len(old) == retrieval.DIM:
                # EWMA with alpha = 0.1 (slow adaptation)
                new_vec = 0.9 * old + 0.1 * vec_arr
                nn = np.linalg.norm(new_vec)
                if nn > 0:
                    new_vec = new_vec / nn
                new_count = (row.get("count") or 0) + 1
                await db.execute(
                    "UPDATE memory_pattern SET query_vec=?, count=?, last_hit=? WHERE slot=?",
                    (db.serialize_f32(new_vec.tolist()), new_count, db.now(), slot),
                )
            return

        await db.execute(
            "INSERT INTO memory_pattern(slot, query_vec, count, last_hit) VALUES(?,?,?,?) "
            "ON CONFLICT(slot) DO UPDATE SET "
            "query_vec=excluded.query_vec, count=count+1, last_hit=excluded.last_hit",
            (slot, db.serialize_f32(vec_arr.tolist()), 1, db.now()),
        )
    except Exception:
        pass
