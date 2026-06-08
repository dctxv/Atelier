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
import math
import re

import numpy as np

from . import db, embeddings

RRF_K = 60
RECENCY_HALF_LIFE = 30 * 86400
CHARS_PER_TOKEN = 4
DOC_MAX_CHUNKS = 6
DIM = db.EMBED_DIM  # 256

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are",
    "was", "were", "be", "with", "at", "by", "it", "this", "that", "these",
    "those", "as", "from", "what", "which", "who", "how", "do", "does", "did",
    "i", "me", "my", "you", "your", "he", "she", "they", "we",
}


# ── Numpy KNN cache ───────────────────────────────────────────────────────────

_knn_mat:     np.ndarray | None = None   # (N, DIM) float32, L2-normalised
_knn_ids:     list[str] = []              # atom IDs parallel to _knn_mat rows
_knn_version: tuple[int, int] = (-1, -1) # (COUNT, MAX_ROWID) invalidation stamp
_knn_lock:    asyncio.Lock | None = None  # created on first use (event loop must exist)


def _get_knn_lock() -> asyncio.Lock:
    global _knn_lock
    if _knn_lock is None:
        _knn_lock = asyncio.Lock()
    return _knn_lock


async def _knn_current_version() -> tuple[int, int]:
    row = await db.fetchone(
        "SELECT COUNT(*) AS n, COALESCE(MAX(rowid), 0) AS mx FROM memory_atom"
    )
    return (row["n"], row["mx"])


async def _rebuild_knn_cache() -> None:
    """Load all memory atom vectors from vec0 shadow tables into numpy (~220ms cold)."""
    global _knn_mat, _knn_ids, _knn_version

    # Snapshot version BEFORE loading so we don't cache a stale stamp.
    version = await _knn_current_version()

    # atom rowid ↔ atom id
    id_rows = await db.fetchall("SELECT rowid, id FROM memory_atom ORDER BY rowid")
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


async def _numpy_knn(serialized_vec: bytes, k: int) -> list[str]:
    """Top-k atom IDs by cosine similarity using the in-memory float32 matrix."""
    await _ensure_knn_cache()
    if _knn_mat is None or _knn_mat.shape[0] == 0:
        return []
    q = np.frombuffer(serialized_vec, dtype=np.float32)
    scores = _knn_mat @ q                          # (N,) cosine similarities
    actual_k = min(k, _knn_mat.shape[0])
    if actual_k == _knn_mat.shape[0]:
        top = np.argsort(scores)[::-1]
    else:
        top = np.argpartition(scores, -actual_k)[-actual_k:]
        top = top[np.argsort(scores[top])[::-1]]
    return [_knn_ids[i] for i in top]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


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
        "WHERE memory_fts MATCH ? ORDER BY rank LIMIT ?",
        (expr, k),
    )
    return [r["id"] for r in rows]


async def _doc_vector_hits(serialized_vec: bytes, k: int) -> list[str]:
    rows = await db.fetchall(
        "SELECT dc.id AS id FROM "
        "(SELECT rowid, distance FROM document_chunk_vec WHERE embedding MATCH ? ORDER BY distance LIMIT ?) v "
        "JOIN document_chunk dc ON dc.rowid = v.rowid ORDER BY v.distance",
        (serialized_vec, k),
    )
    return [r["id"] for r in rows]


async def _doc_fts_hits(query: str, k: int) -> list[str]:
    expr = _fts_query(query)
    if not expr:
        return []
    rows = await db.fetchall(
        "SELECT dc.id AS id FROM document_chunk_fts f "
        "JOIN document_chunk dc ON dc.rowid = f.rowid "
        "WHERE document_chunk_fts MATCH ? ORDER BY rank LIMIT ?",
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

async def retrieve(query: str, k: int = 12, budget_tokens: int = 700) -> list[dict]:
    query = (query or "").strip()
    if not query:
        return []

    # Single embed call — pre-serialized bytes shared by all vector functions.
    vec = await embeddings.embed(query)
    sv = db.serialize_f32(vec)

    # Run all reads concurrently — the ready_doc_ids check is merged into the
    # gather so there's zero sequential overhead on the hot path.
    # Doc queries use DOC_MAX_CHUNKS as the limit (we cap there anyway; querying
    # for k=12 and ranking 12 BM25 results is wasted work).
    doc_k = DOC_MAX_CHUNKS
    (
        numpy_ids, fts_ids, doc_vec_ids, doc_fts_ids, pinned, ready_rows
    ) = await asyncio.gather(
        _numpy_knn(sv, k),
        _fts_hits(query, k),
        _doc_vector_hits(sv, doc_k),
        _doc_fts_hits(query, doc_k),
        db.fetchall("SELECT * FROM memory_atom WHERE pinned=1 ORDER BY created_at DESC"),
        db.fetchall("SELECT id FROM document WHERE status='ready'"),
    )
    ready_doc_ids = {r["id"] for r in ready_rows}
    has_docs = bool(ready_doc_ids)
    if not has_docs:
        doc_vec_ids, doc_fts_ids = [], []

    mem_scores = _rrf([numpy_ids, fts_ids])
    doc_scores = _rrf([doc_vec_ids, doc_fts_ids])

    pinned_ids = {p["id"] for p in pinned}
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

    def mem_final_score(r: dict) -> float:
        base = mem_scores.get(r["id"], 0.0)
        if r["id"] in pinned_ids:
            base += 1.0
        return base + _recency_boost(r.get("created_at"))

    all_items: list[dict] = []

    for r in mem_rows.values():
        all_items.append({
            "id":          r["id"],
            "text":        r["text"],
            "type":        r.get("type"),
            "source_kind": r.get("source_kind"),
            "source_id":   r.get("source_id"),
            "created_at":  r.get("created_at"),
            "pinned":      bool(r.get("pinned")),
            "score":       round(mem_final_score(r), 4),
            "source_type": "memory",
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


def format_block(atoms: list[dict]) -> str:
    if not atoms:
        return ""
    mem_items = [a for a in atoms if a.get("source_type") != "document"]
    doc_items  = [a for a in atoms if a.get("source_type") == "document"]
    lines: list[str] = []
    if mem_items:
        lines.append("[MEMORY] Relevant things I know about the user (use naturally, don't list verbatim):")
        for a in mem_items:
            lines.append(f"- {a['text']}")
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
