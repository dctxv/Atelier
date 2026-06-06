"""Hybrid retrieval over the shared memory store (Part 1.3).

One function — retrieve() — serves chat, the notes co-writer, and drafts.
Pipeline:
  embed query
  -> vector top-K (sqlite-vec)  UNION  keyword hits (FTS5)
  -> fuse with Reciprocal Rank Fusion
  -> recency boost
  -> always include pinned atoms
  -> trim to a token budget (hot-path rule 4: hard cap, default ~700 tokens)
"""
from __future__ import annotations

import asyncio
import math
import re

from . import db, embeddings

RRF_K = 60          # standard RRF damping constant
RECENCY_HALF_LIFE = 30 * 86400  # 30 days, in seconds
CHARS_PER_TOKEN = 4  # rough token estimate, good enough for budgeting

# Ultra-common words blow up FTS bm25 (they match a huge fraction of rows). The
# vector side already covers semantics, so dropping these from the keyword query
# is a pure win — it was the dominant cost on common-word queries in the Part 4
# scaling test (~55ms -> negligible at 50k atoms).
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are",
    "was", "were", "be", "with", "at", "by", "it", "this", "that", "these",
    "those", "as", "from", "what", "which", "who", "how", "do", "does", "did",
    "i", "me", "my", "you", "your", "he", "she", "they", "we",
}


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def _fts_query(query: str) -> str:
    """Build a safe FTS5 MATCH expression: OR of quoted, non-stopword tokens."""
    tokens = [t for t in re.findall(r"[a-z0-9]+", query.lower())
              if t not in _STOPWORDS and len(t) > 1]
    return " OR ".join(f'"{t}"' for t in tokens) if tokens else ""


async def _vector_hits(query: str, k: int) -> list[str]:
    vec = await embeddings.embed(query)
    rows = await db.fetchall(
        "SELECT m.id AS id FROM "
        "(SELECT rowid, distance FROM memory_vec WHERE embedding MATCH ? ORDER BY distance LIMIT ?) v "
        "JOIN memory_atom m ON m.rowid = v.rowid ORDER BY v.distance",
        (db.serialize_f32(vec), k),
    )
    return [r["id"] for r in rows]


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


def _rrf(ranked_lists: list[list[str]]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, atom_id in enumerate(ranked):
            scores[atom_id] = scores.get(atom_id, 0.0) + 1.0 / (RRF_K + rank + 1)
    return scores


def _recency_boost(created_at: int | None) -> float:
    if not created_at:
        return 0.0
    age = max(0, db.now() - created_at)
    return 0.5 * math.exp(-age / RECENCY_HALF_LIFE)


async def retrieve(query: str, k: int = 12, budget_tokens: int = 700) -> list[dict]:
    query = (query or "").strip()
    if not query:
        return []

    # Run the independent reads concurrently — the WAL read pool lets the vector
    # scan, the FTS scan, and the pinned lookup overlap instead of summing.
    vec_ids, fts_ids, pinned = await asyncio.gather(
        _vector_hits(query, k),
        _fts_hits(query, k),
        db.fetchall("SELECT * FROM memory_atom WHERE pinned=1 ORDER BY created_at DESC"),
    )

    scores = _rrf([vec_ids, fts_ids])
    pinned_ids = {p["id"] for p in pinned}

    candidate_ids = set(scores) | pinned_ids
    if not candidate_ids:
        return []

    placeholders = ",".join("?" * len(candidate_ids))
    rows = await db.fetchall(
        f"SELECT * FROM memory_atom WHERE id IN ({placeholders})", tuple(candidate_ids)
    )
    by_id = {r["id"]: r for r in rows}

    def final_score(r: dict) -> float:
        base = scores.get(r["id"], 0.0)
        if r["id"] in pinned_ids:
            base += 1.0  # pinned float to the top
        return base + _recency_boost(r.get("created_at"))

    ordered = sorted(by_id.values(), key=final_score, reverse=True)

    # Trim to the token budget.
    out: list[dict] = []
    used = 0
    for r in ordered:
        cost = _estimate_tokens(r["text"])
        if used + cost > budget_tokens and out:
            break
        out.append(
            {
                "id": r["id"],
                "text": r["text"],
                "type": r.get("type"),
                "source_kind": r.get("source_kind"),
                "source_id": r.get("source_id"),
                "created_at": r.get("created_at"),
                "pinned": bool(r.get("pinned")),
                "score": round(final_score(r), 4),
            }
        )
        used += cost
    return out


def format_block(atoms: list[dict]) -> str:
    """Render retrieved atoms as a compact MEMORY block for a system prompt."""
    if not atoms:
        return ""
    lines = ["[MEMORY] Relevant things I know about the user (use naturally, don't list verbatim):"]
    for a in atoms:
        lines.append(f"- {a['text']}")
    return "\n".join(lines)
