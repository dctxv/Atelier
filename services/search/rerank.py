"""Local-embedding rerank, near-duplicate removal, token-budgeted chunking
(Part 5 E2-E3). Reuses v1 embeddings (cached) — never a paid reranker.
"""
from __future__ import annotations

import numpy as np

from .. import embeddings
from .schema import SearchResult

NEAR_DUP_THRESHOLD = 0.97
CHARS_PER_TOKEN = 4


def _text_for(res: SearchResult) -> str:
    return f"{res.title}. {res.snippet} {res.content or ''}".strip()


async def _embed_all(results: list[SearchResult]) -> list[np.ndarray]:
    vecs = []
    for r in results:
        v = await embeddings.embed(_text_for(r)[:2000])
        vecs.append(np.asarray(v, dtype=np.float32))
    return vecs


async def rerank_and_dedup(query: str, results: list[SearchResult]) -> list[SearchResult]:
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

    # Score by cosine similarity to the query (vectors are L2-normalized).
    for r, v in zip(results, vecs):
        r.score = float(np.dot(qv, v))

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
