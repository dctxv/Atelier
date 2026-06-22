"""Hybrid retrieval over the shared memory + document store (Part 1.3 + RAG).

One function — retrieve() — serves chat, the notes co-writer, and drafts.
Pipeline:
  embed query  (ONCE — shared by all vector functions)
  -> in-memory numpy KNN for memory atoms  (4ms vs 115ms for sqlite-vec full scan)
  -> sqlite-vec KNN for document chunks    (4k entries — fast enough at <12ms)
  -> FTS5 BM25 for both sources
  -> fuse with Reciprocal Rank Fusion (per-source, then merged)
  -> recency boost for memory atoms (documents don't decay — they're references)
  -> always include pinned atoms
  -> document dominance cap (max DOC_MAX_CHUNKS per query)
  -> trim to a token budget (hot-path rule 4: hard cap, default ~700 tokens)

Performance design:
  - Numpy KNN cache: all memory atom vectors are loaded from vec0 shadow tables
    into a float32 numpy matrix (50k * 256 * 4 = ~51 MB). Cold load is ~220ms,
    done once on first request or after any atom change. Warm numpy @ query takes
    ~4ms vs ~115ms for sqlite-vec full scan on this hardware.
  - Version stamp: COUNT(*) + MAX(rowid) is checked on every call (~1ms). Cache
    is only rebuilt when atoms change.
  - Partial index on memory_atom(pinned) WHERE pinned=1 cuts pinned lookup from
    18ms to <0.2ms.
  - Doc queries skip the JOIN to the document table; status checked in Python.
  - Read pool sized at 8 threads so 5 concurrent reads fit without queueing.

Each result carries source_type = "memory" | "document" so callers can filter
or format differently.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import math
import re

import numpy as np

from . import db, embeddings
from .intent import MODE_POLICIES

RRF_K = 60
RECENCY_HALF_LIFE = 30 * 86400
CHARS_PER_TOKEN = 4
DOC_MAX_CHUNKS = 6
DIM = db.EMBED_DIM  # 256
PROJECT_OVERFETCH = 6  # over-fetch factor before project filter [VALIDATE]
KNN_MIN_COS = 0.25     # min cosine for a memory atom to count as relevant [VALIDATE]

# ── W1: cognitive-mode retrieval policies ─────────────────────────────────────
# The per-mode policy table (MODE_POLICIES) lives in services.intent so it stays
# importable without numpy and the suppression invariants stay unit-testable.
# Personal-flavoured atom signals used by suppress_personal (technical mode).
_PERSONAL_MODALITIES = {"opinion", "desire", "self_perception"}
_PERSONAL_CATEGORIES = {"attribute"}


async def policy_for(mode: str) -> dict:
    """Return the retrieval policy for a cognitive mode, merged with any runtime
    overrides stored in app_config under "retrieval.mode_policies" (JSON)."""
    base = dict(MODE_POLICIES.get(mode, MODE_POLICIES["factual"]))
    try:
        row = await db.fetchone(
            "SELECT value FROM app_config WHERE key='retrieval.mode_policies'"
        )
        if row and row.get("value"):
            overrides = json.loads(row["value"]) or {}
            if isinstance(overrides.get(mode), dict):
                base.update(overrides[mode])
    except Exception:
        pass
    return base

# ── Read-time confidence decay (Living Memory v2) ─────────────────────────────
# Grace period and half-life per predicate_category.  All [VALIDATE] against
# real usage once a week of data accumulates.
_DECAY_PARAMS: dict[str | None, tuple[int | None, int | None]] = {
    "functional":   (365 * 86400, 365 * 86400),
    "multi_valued": (180 * 86400, 240 * 86400),
    "comparative":  (120 * 86400, 180 * 86400),
    "experiential": (None, None),           # never decays
    "attribute":    (270 * 86400, 365 * 86400),
    None:           (90 * 86400, 180 * 86400),  # legacy atoms without category
}
FADING_THRESHOLD = 0.4  # effective_confidence below this → faded (excluded by default)

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are",
    "was", "were", "be", "with", "at", "by", "it", "this", "that", "these",
    "those", "as", "from", "what", "which", "who", "how", "do", "does", "did",
    "i", "me", "my", "you", "your", "he", "she", "they", "we",
}


# ── Numpy KNN cache ───────────────────────────────────────────────────────────

_knn_mat:     np.ndarray | None = None      # (N, DIM) float32, L2-normalised
_knn_ids:     list[str] = []               # atom IDs parallel to _knn_mat rows
_knn_version: tuple[int, int, int] = (-1, -1, -1)  # (COUNT, MAX_ROWID, MUTATION_SEQ)
_knn_lock:    asyncio.Lock | None = None   # created on first use (event loop must exist)


def _get_knn_lock() -> asyncio.Lock:
    global _knn_lock
    if _knn_lock is None:
        _knn_lock = asyncio.Lock()
    return _knn_lock


async def _knn_current_version() -> tuple[int, int, int]:
    """(count, max_rowid, mutation_seq) — mutation_seq catches in-place updates."""
    row = await db.fetchone(
        "SELECT COUNT(*) AS n, COALESCE(MAX(rowid),0) AS mx "
        "FROM memory_atom WHERE status='active' OR status IS NULL"
    )
    seq_row = await db.fetchone("SELECT value FROM app_config WHERE key='memory_mutation_seq'")
    seq = int(seq_row["value"]) if seq_row else 0
    return (row["n"], row["mx"], seq)


async def _rebuild_knn_cache() -> None:
    """Load only *active* memory atom vectors from vec0 shadow tables into numpy."""
    global _knn_mat, _knn_ids, _knn_version

    # Snapshot version BEFORE loading so we don't cache a stale stamp.
    version = await _knn_current_version()

    # Only include active (or legacy/NULL-status) atoms in the KNN matrix.
    id_rows = await db.fetchall(
        "SELECT rowid, id FROM memory_atom WHERE status='active' OR status IS NULL ORDER BY rowid"
    )
    rowid_to_id = {r["rowid"]: r["id"] for r in id_rows}

    # Raw vector blobs from shadow table (packed float32, chunk_size * DIM per blob).
    chunk_blobs: dict[int, np.ndarray] = {}
    for r in await db.fetchall(
        "SELECT rowid, vectors FROM memory_vec_vector_chunks00 ORDER BY rowid"
    ):
        chunk_blobs[r["rowid"]] = np.frombuffer(bytes(r["vectors"]), dtype=np.float32)

    # Rowid → position mapping inside chunks.
    pos_rows = await db.fetchall(
        "SELECT rowid, chunk_id, chunk_offset FROM memory_vec_rowids ORDER BY rowid"
    )

    ids: list[str] = []
    vecs: list[np.ndarray] = []
    for r in pos_rows:
        aid = rowid_to_id.get(r["rowid"])
        blob = chunk_blobs.get(r["chunk_id"])
        if aid is None or blob is None:
            continue
        s = r["chunk_offset"] * DIM
        if s + DIM <= len(blob):
            ids.append(aid)
            vecs.append(blob[s: s + DIM])

    _knn_mat = np.stack(vecs) if vecs else np.empty((0, DIM), dtype=np.float32)
    _knn_ids = ids
    _knn_version = version


async def _ensure_knn_cache() -> None:
    """Refresh cache if atom set has changed since last load. Hot path: ~1ms."""
    global _knn_mat
    version = await _knn_current_version()
    if _knn_mat is not None and version == _knn_version:
        return
    async with _get_knn_lock():
        version = await _knn_current_version()
        if _knn_mat is not None and version == _knn_version:
            return
        await _rebuild_knn_cache()


async def _numpy_knn(serialized_vec: bytes, k: int,
                     project_id: str | None = None,
                     min_cos: float | None = None) -> list[str]:
    """Top-k atom IDs by cosine similarity.

    min_cos overrides the module relevance floor (KNN_MIN_COS) — the cognitive
    mode (W1) raises it for high-precision modes so over-fetching is suppressed.

    When project_id is given: over-fetch by PROJECT_OVERFETCH, then filter to
    atoms in this project OR globally-pinned. This avoids under-return when the
    global top-k are all from other projects.
    """
    floor = KNN_MIN_COS if min_cos is None else min_cos
    if k <= 0:
        return []
    await _ensure_knn_cache()
    if _knn_mat is None or _knn_mat.shape[0] == 0:
        return []
    q = np.frombuffer(serialized_vec, dtype=np.float32)
    qn = np.linalg.norm(q)
    if qn > 0:
        q = q / qn                                 # normalise so scores are true cosine
    scores = _knn_mat @ q                          # (N,) cosine similarities

    if project_id is None:
        actual_k = min(k, _knn_mat.shape[0])
        if actual_k == _knn_mat.shape[0]:
            top = np.argsort(scores)[::-1]
        else:
            top = np.argpartition(scores, -actual_k)[-actual_k:]
            top = top[np.argsort(scores[top])[::-1]]
        # Relevance floor: don't return atoms that are merely "nearest" when none
        # are actually similar (otherwise every query injects irrelevant memory).
        return [_knn_ids[i] for i in top if scores[i] >= floor]

    # Project-scoped: over-fetch then filter
    raw_k = min(k * PROJECT_OVERFETCH, _knn_mat.shape[0])
    top = np.argpartition(scores, -raw_k)[-raw_k:]
    top = top[np.argsort(scores[top])[::-1]]
    return [_knn_ids[i] for i in top if scores[i] >= floor]  # caller filters to project


# ── Helpers ───────────────────────────────────────────────────────────────────

def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def _effective_confidence(atom: dict, now_ts: int) -> float:
    """Read-time confidence with temporal decay. Pinned atoms never fade."""
    if atom.get("pinned"):
        return atom.get("confidence") or 1.0
    stored_conf = atom.get("confidence")
    if stored_conf is None:
        stored_conf = 1.0  # legacy atom: treat as fully confident

    cat = atom.get("predicate_category")
    grace, half_life = _DECAY_PARAMS.get(cat, _DECAY_PARAMS[None])

    if grace is None:  # experiential — never decays
        return stored_conf

    anchor = atom.get("last_used_at") or atom.get("created_at") or now_ts
    age = max(0, now_ts - anchor)
    if age <= grace:
        return stored_conf

    decay_age = age - grace
    decay_factor = math.exp(-math.log(2) * decay_age / half_life)
    return max(0.05, stored_conf * decay_factor)


def _fts_query(query: str) -> str:
    tokens = [t for t in re.findall(r"[a-z0-9]+", query.lower())
              if t not in _STOPWORDS and len(t) > 1]
    return " OR ".join(f'"{t}"' for t in tokens) if tokens else ""


# ── FTS hit functions ─────────────────────────────────────────────────────────

async def _fts_hits(query: str, k: int) -> list[str]:
    expr = _fts_query(query)
    if not expr:
        return []
    rows = await db.fetchall(
        "SELECT m.id AS id FROM memory_fts f JOIN memory_atom m ON m.rowid = f.rowid "
        "WHERE memory_fts MATCH ? AND (m.status='active' OR m.status IS NULL) "
        "ORDER BY rank LIMIT ?",
        (expr, k),
    )
    return [r["id"] for r in rows]


async def _doc_vector_hits(serialized_vec: bytes, k: int,
                           project_id: str | None = None) -> list[str]:
    if project_id is not None:
        # Over-fetch subquery, then filter to this project's documents
        rows = await db.fetchall(
            "SELECT dc.id AS id FROM "
            "(SELECT rowid, distance FROM document_chunk_vec WHERE embedding MATCH ? "
            " ORDER BY distance LIMIT ?) v "
            "JOIN document_chunk dc ON dc.rowid = v.rowid "
            "JOIN document d ON d.id = dc.document_id "
            "WHERE d.project_id = ? AND d.status = 'ready' "
            "ORDER BY v.distance LIMIT ?",
            (serialized_vec, k * PROJECT_OVERFETCH, project_id, k),
        )
    else:
        # Global: over-fetch then exclude project-scoped documents so project
        # files never bleed into the main chat (symmetric to memory atoms below).
        rows = await db.fetchall(
            "SELECT dc.id AS id FROM "
            "(SELECT rowid, distance FROM document_chunk_vec WHERE embedding MATCH ? ORDER BY distance LIMIT ?) v "
            "JOIN document_chunk dc ON dc.rowid = v.rowid "
            "JOIN document d ON d.id = dc.document_id "
            "WHERE d.project_id IS NULL ORDER BY v.distance LIMIT ?",
            (serialized_vec, k * PROJECT_OVERFETCH, k),
        )
    return [r["id"] for r in rows]


async def _doc_fts_hits(query: str, k: int,
                        project_id: str | None = None) -> list[str]:
    expr = _fts_query(query)
    if not expr:
        return []
    if project_id is not None:
        rows = await db.fetchall(
            "SELECT dc.id AS id FROM document_chunk_fts f "
            "JOIN document_chunk dc ON dc.rowid = f.rowid "
            "JOIN document d ON d.id = dc.document_id "
            "WHERE document_chunk_fts MATCH ? AND d.project_id = ? ORDER BY rank LIMIT ?",
            (expr, project_id, k),
        )
    else:
        # Global: exclude project-scoped documents (see _doc_vector_hits).
        rows = await db.fetchall(
            "SELECT dc.id AS id FROM document_chunk_fts f "
            "JOIN document_chunk dc ON dc.rowid = f.rowid "
            "JOIN document d ON d.id = dc.document_id "
            "WHERE document_chunk_fts MATCH ? AND d.project_id IS NULL ORDER BY rank LIMIT ?",
            (expr, k),
        )
    return [r["id"] for r in rows]


# ── RRF ───────────────────────────────────────────────────────────────────────

def _rrf(ranked_lists: list[list[str]]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, item_id in enumerate(ranked):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (RRF_K + rank + 1)
    return scores


def _recency_boost(created_at: int | None) -> float:
    if not created_at:
        return 0.0
    age = max(0, db.now() - created_at)
    return 0.5 * math.exp(-age / RECENCY_HALF_LIFE)


# ── Public interface ──────────────────────────────────────────────────────────

async def _empty() -> list:
    return []


async def retrieve(
    query: str,
    k: int = 12,
    budget_tokens: int = 700,
    project_id: str | None = None,
    include_faded: bool = False,
    as_of: int | None = None,
    policy: dict | None = None,
) -> list[dict]:
    """Hybrid retrieval with Living Memory v2 decay and temporal filtering.

    include_faded: when True, include atoms whose effective_confidence is below
                   FADING_THRESHOLD (normally excluded from retrieval).
    as_of:         epoch-seconds timestamp; when given, only return atoms whose
                   validity range contained that point in time (time-travel).
    policy:        W1 cognitive-mode policy (see MODE_POLICIES). When given it
                   gates AMBIENT memory/doc recall and tunes k/min_cos/budget.
                   Pinned atoms are ALWAYS included regardless of policy, so the
                   gate can suppress noise without ever dropping protected
                   context. When None, behaviour is unchanged (back-compat).
    """
    query = (query or "").strip()
    if not query:
        return []

    pol = policy or {}
    inject_memory     = pol.get("inject_memory", True)
    inject_docs       = pol.get("inject_docs", True)
    k_mem             = pol.get("k", k) if inject_memory else 0
    min_cos           = pol.get("min_cos")          # None → module default floor
    suppress_personal = pol.get("suppress_personal", False)
    if policy is not None and pol.get("budget_tokens") is not None:
        budget_tokens = pol["budget_tokens"]

    # Single embed call — pre-serialized bytes shared by all vector functions.
    vec = await embeddings.embed(query)
    sv = db.serialize_f32(vec)

    doc_k = DOC_MAX_CHUNKS
    (
        numpy_ids_raw, fts_ids, doc_vec_ids, doc_fts_ids, pinned, ready_rows
    ) = await asyncio.gather(
        _numpy_knn(sv, k_mem, project_id=project_id, min_cos=min_cos) if inject_memory else _empty(),
        _fts_hits(query, k_mem) if inject_memory else _empty(),
        _doc_vector_hits(sv, doc_k, project_id=project_id) if inject_docs else _empty(),
        _doc_fts_hits(query, doc_k, project_id=project_id) if inject_docs else _empty(),
        db.fetchall("SELECT * FROM memory_atom WHERE pinned=1 ORDER BY created_at DESC"),
        db.fetchall("SELECT id FROM document WHERE status='ready'"),
    )

    # Project-scope the memory KNN results (numpy path over-fetched raw)
    pinned_ids = {p["id"] for p in pinned}
    if project_id is not None:
        # Fetch this project's atom IDs for filtering
        project_atom_rows = await db.fetchall(
            "SELECT id FROM memory_atom WHERE project_id=?", (project_id,)
        )
        project_atom_ids = {r["id"] for r in project_atom_rows}
        allowed_ids = project_atom_ids | pinned_ids
        numpy_ids = [aid for aid in numpy_ids_raw if aid in allowed_ids][:k_mem]
        # Also scope FTS hits
        fts_ids = [fid for fid in fts_ids if fid in allowed_ids]
    else:
        # Global: exclude project-scoped atoms (they shouldn't bleed into global chat)
        project_only_rows = await db.fetchall(
            "SELECT id FROM memory_atom WHERE project_id IS NOT NULL AND project_id != ''"
        )
        project_only_ids = {r["id"] for r in project_only_rows}
        numpy_ids = [aid for aid in numpy_ids_raw if aid not in project_only_ids][:k_mem]
        fts_ids   = [fid for fid in fts_ids if fid not in project_only_ids]

    ready_doc_ids = {r["id"] for r in ready_rows}
    has_docs = bool(ready_doc_ids)
    if not has_docs:
        doc_vec_ids, doc_fts_ids = [], []

    mem_scores = _rrf([numpy_ids, fts_ids])
    doc_scores = _rrf([doc_vec_ids, doc_fts_ids])

    mem_candidate_ids = set(mem_scores) | pinned_ids

    doc_capped_ids = {
        cid for cid, _ in sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)[:DOC_MAX_CHUNKS]
    }

    mem_rows: dict[str, dict] = {}
    if mem_candidate_ids:
        placeholders = ",".join("?" * len(mem_candidate_ids))
        rows = await db.fetchall(
            f"SELECT * FROM memory_atom WHERE id IN ({placeholders})", tuple(mem_candidate_ids)
        )
        mem_rows = {r["id"]: r for r in rows}

    doc_rows: dict[str, dict] = {}
    if doc_capped_ids and ready_doc_ids:
        placeholders = ",".join("?" * len(doc_capped_ids))
        rows = await db.fetchall(
            f"SELECT dc.*, d.filename FROM document_chunk dc "
            f"JOIN document d ON d.id = dc.document_id "
            f"WHERE dc.id IN ({placeholders})",
            tuple(doc_capped_ids),
        )
        doc_rows = {r["id"]: r for r in rows if r["document_id"] in ready_doc_ids}

    now_ts = db.now()

    # Apply fading filter: atoms with effective_confidence < threshold are
    # excluded from default retrieval (they remain visible via include_faded=True).
    if not include_faded:
        mem_rows = {
            k: v for k, v in mem_rows.items()
            if v.get("pinned") or _effective_confidence(v, now_ts) >= FADING_THRESHOLD
        }

    # Apply as_of filter: only return atoms whose validity range contained that timestamp.
    if as_of is not None:
        mem_rows = {
            k: v for k, v in mem_rows.items()
            if (v.get("valid_from") or 0) <= as_of
            and (v.get("valid_until") is None or v.get("valid_until") >= as_of)
        }

    # Invariants G3f + G5f: suppression atoms and hypothesis atoms NEVER reach chat context.
    # W2 Visibility Law: a proposed/rejected inference is never "believed" — it
    # must not influence an answer until the user has confirmed it (status→active).
    mem_rows = {
        k: v for k, v in mem_rows.items()
        if v.get("predicate") != "suppressed"
        and v.get("modality") != "hypothesis"
        and (v.get("status") in (None, "active"))
    }

    # W1: technical mode suppresses personal-flavoured atoms (opinions, desires,
    # traits, self-perception) so a debugging turn doesn't pull in life facts.
    # Pinned atoms are never dropped.
    if suppress_personal:
        mem_rows = {
            k: v for k, v in mem_rows.items()
            if v.get("pinned")
            or (v.get("modality") not in _PERSONAL_MODALITIES
                and v.get("predicate_category") not in _PERSONAL_CATEGORIES)
        }

    # Prescient-only stale-self-image guard (P1.2): annotate superseded atoms.
    tier_row = await db.fetchone("SELECT value FROM app_config WHERE key='memory.tier'")
    if tier_row and tier_row.get("value") == "prescient":
        await _annotate_stale_self_image(mem_rows)

    def mem_final_score(r: dict) -> float:
        base = mem_scores.get(r["id"], 0.0)
        if r["id"] in pinned_ids:
            base += 1.0
        ec = _effective_confidence(r, now_ts)
        return (base + _recency_boost(r.get("created_at"))) * ec

    all_items: list[dict] = []

    for r in mem_rows.values():
        all_items.append({
            "id":                r["id"],
            "text":              r["text"],
            "type":              r.get("type"),
            "source_kind":       r.get("source_kind"),
            "source_id":         r.get("source_id"),
            "created_at":        r.get("created_at"),
            "pinned":            bool(r.get("pinned")),
            "score":             round(mem_final_score(r), 4),
            "source_type":       "memory",
            # Structured fields threaded for guard + (inferred) tag (Fix 1)
            "modality":          r.get("modality"),
            "predicate":         r.get("predicate"),
            "subject":           r.get("subject"),
            "predicate_category": r.get("predicate_category"),
            "valid_from":        r.get("valid_from"),
            "meta":              json.loads(r["meta"]) if r.get("meta") else None,
        })

    for chunk_id, row in doc_rows.items():
        all_items.append({
            "id":          row["id"],
            "text":        row["text"],
            "type":        "document_chunk",
            "source_kind": "document",
            "source_id":   row["document_id"],
            "created_at":  row.get("created_at"),
            "pinned":      False,
            "score":       round(doc_scores.get(chunk_id, 0.0), 4),
            "source_type": "document",
            "filename":    row.get("filename"),
            "char_start":  row.get("char_start"),
            "char_end":    row.get("char_end"),
        })

    ordered = sorted(all_items, key=lambda x: x["score"], reverse=True)

    out: list[dict] = []
    used = 0
    for r in ordered:
        cost = _estimate_tokens(r["text"])
        if used + cost > budget_tokens and out:
            break
        out.append(r)
        used += cost
    return out


async def _annotate_stale_self_image(mem_rows: dict) -> None:
    """For self_perception / attribute atoms, append '(as of Mon YYYY)' when
    superseded by a newer atom in the same (subject, predicate) chain.

    Stamp uses the *superseded atom's own* assertion date so the model reads
    "this was true then, may be stale" rather than implying the newer date
    is when it stopped being true.

    One batched SQL query per (subject, predicate) pair; total cost < 1ms.
    """
    pairs = {
        (r.get("subject"), r.get("predicate"))
        for r in mem_rows.values()
        if r.get("subject") and r.get("predicate")
        and (
            r.get("modality") == "self_perception"
            or r.get("predicate_category") == "attribute"
        )
    }
    if not pairs:
        return

    for subj, pred in pairs:
        newest_row = await db.fetchone(
            "SELECT MAX(COALESCE(valid_from, created_at)) AS mx FROM memory_atom "
            "WHERE subject=? AND predicate=? AND (status='active' OR status IS NULL)",
            (subj, pred),
        )
        newest = newest_row["mx"] if newest_row else None
        if not newest:
            continue
        for r in mem_rows.values():
            if (r.get("subject"), r.get("predicate")) != (subj, pred):
                continue
            own_ts = r.get("valid_from") or r.get("created_at") or 0
            if newest > own_ts:
                # Stamp with this atom's own assertion date (not the newer atom's date)
                stamp = datetime.datetime.fromtimestamp(own_ts).strftime("%b %Y")
                r["text"] = f"{r['text']} (as of {stamp})"


def format_block(atoms: list[dict]) -> str:
    if not atoms:
        return ""
    mem_items = [a for a in atoms if a.get("source_type") != "document"]
    doc_items  = [a for a in atoms if a.get("source_type") == "document"]
    lines: list[str] = []
    if mem_items:
        lines.append("[MEMORY] Relevant things I know about the user (use naturally, don't list verbatim):")
        for a in mem_items:
            # (inferred) tag: insight atoms are unconfirmed inferences — shown before believed
            tag = " (inferred)" if a.get("modality") == "insight" else ""
            lines.append(f"- {a['text']}{tag}")
    if doc_items:
        if lines:
            lines.append("")
        lines.append("[DOCUMENTS] Relevant passages from the user's uploaded files:")
        for a in doc_items:
            fname = a.get("filename") or "document"
            lines.append(f"- [{fname}] {a['text']}")
    return "\n".join(lines)


def doc_sources(atoms: list[dict]) -> list[str]:
    seen: list[str] = []
    for a in atoms:
        fn = a.get("filename")
        if a.get("source_type") == "document" and fn and fn not in seen:
            seen.append(fn)
    return seen
