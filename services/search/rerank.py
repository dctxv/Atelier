"""Local-embedding rerank, near-duplicate removal, token-budgeted chunking
(Part 5 E2-E3). Reuses v1 embeddings (cached) — never a paid reranker.

Deep Research v2: accepts an optional freshness_cls dict and applies exponential
recency decay to scores when the query is time-sensitive.
"""
from __future__ import annotations

import math
import time

import numpy as np

from .. import embeddings
from .schema import SearchResult

NEAR_DUP_THRESHOLD = 0.97
CHARS_PER_TOKEN = 4

_LN2 = math.log(2)

# Recency half-lives by tier (hours). Larger = slower decay.
_HALF_LIFE = {
    "breaking": 2,
    "news":     24,
    "fresh":    48,
}


def _text_for(res: SearchResult) -> str:
    return f"{res.title}. {res.snippet} {res.content or ''}".strip()


async def _embed_all(results: list[SearchResult]) -> list[np.ndarray]:
    vecs = []
    for r in results:
        v = await embeddings.embed(_text_for(r)[:2000])
        vecs.append(np.asarray(v, dtype=np.float32))
    return vecs


def _recency_weight(published_at: int | None, half_life_h: float) -> float:
    """Exponential decay: 1.0 when just published, 0.5 at half_life_h, etc."""
    if not published_at:
        return 0.0
    age_h = (time.time() - published_at) / 3600
    return math.exp(-_LN2 * age_h / half_life_h)


async def rerank_and_dedup(
    query: str,
    results: list[SearchResult],
    freshness_cls: dict | None = None,
) -> list[SearchResult]:
    if not results:
        return results

    # Exact-URL dedup first (cheap).
    seen_urls, unique = set(), []
    for r in results:
        u = r.url.rstrip("/")
        if u and u not in seen_urls:
            seen_urls.add(u)
            unique.append(r)
    results = unique

    qv = np.asarray(await embeddings.embed(query), dtype=np.float32)
    vecs = await _embed_all(results)

    # Determine recency weighting from freshness class.
    cls = freshness_cls or {}
    if cls.get("is_breaking"):
        alpha, beta, half_life = 0.70, 0.30, _HALF_LIFE["breaking"]
    elif cls.get("volatile") or cls.get("is_news"):
        alpha, beta, half_life = 0.90, 0.10, _HALF_LIFE["news"]
    elif cls.get("fresh"):
        alpha, beta, half_life = 0.90, 0.10, _HALF_LIFE["fresh"]
    else:
        alpha, beta, half_life = 1.00, 0.00, None

    for r, v in zip(results, vecs):
        cos = float(np.dot(qv, v))
        if beta and half_life and r.published_at:
            rec = _recency_weight(r.published_at, half_life)
            r.score = alpha * cos + beta * rec
        else:
            r.score = cos

    order = sorted(range(len(results)), key=lambda i: results[i].score, reverse=True)

    # Near-duplicate removal in ranked order: drop a result too similar to one
    # already kept.
    kept_idx: list[int] = []
    out: list[SearchResult] = []
    for i in order:
        dup = False
        for j in kept_idx:
            if float(np.dot(vecs[i], vecs[j])) >= NEAR_DUP_THRESHOLD:
                dup = True
                break
        if not dup:
            kept_idx.append(i)
            out.append(results[i])
    return out


def chunk(results: list[SearchResult], budget_tokens: int = 2000,
          chunk_chars: int = 1000) -> list[dict]:
    """Token-budgeted chunks across the top results (for downstream grounding)."""
    chunks: list[dict] = []
    used = 0
    for r in results:
        body = (r.content or r.snippet or "").strip()
        if not body:
            continue
        for i in range(0, len(body), chunk_chars):
            piece = body[i:i + chunk_chars]
            cost = max(1, len(piece) // CHARS_PER_TOKEN)
            if used + cost > budget_tokens and chunks:
                return chunks
            chunks.append({"url": r.url, "title": r.title, "text": piece,
                           "published_at": r.published_at})
            used += cost
    return chunks
