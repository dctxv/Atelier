"""The orchestrator (Part 1): runs the seven layers and returns a SearchResponse.

query → freshness → cache → router → providers → extraction → rerank/dedup →
output contract. This is the function consumers call.
"""
from __future__ import annotations

from . import cache, extraction, freshness, obs, rerank, router
from .schema import SearchResponse


async def search(
    query: str,
    *,
    max_results: int = 8,
    top_k: int = 4,
    want_content: bool = False,
    recency: str | None = None,     # force a window; None = let the classifier decide
    use_cache: bool = True,
    drop_stale: bool = False,
) -> SearchResponse:
    query = (query or "").strip()
    if not query:
        return SearchResponse(query=query)

    # [1] Freshness classifier (local, <30ms).
    cls = freshness.classify(query)
    recency_param = recency if recency is not None else freshness.recency_param(cls)
    is_news = cls["is_news"]
    ttl = freshness.ttl_for(cls)

    params = {"recency": recency_param, "is_news": is_news, "max_results": max_results,
              "top_k": top_k, "want_content": want_content,
              "order": await router.registry.order()}
    key = cache.params_hash(query, params)
    norm = cache.normalize_query(query)

    # [2] Cache lookup.
    if use_cache:
        hit = await cache.get(key)
        if hit is not None:
            obs.record_query(from_cache=True, cost_units=0, fresh=cls["fresh"],
                             fresh_covered=bool(hit.as_of))
            return hit

    # [3-4] Provider router + providers.
    results, providers_used, cost_units = await router.route(
        query, max_results=max_results, recency=recency_param, is_news=is_news,
        include_raw_content=want_content,
    )

    # [5] Extraction + stale-link / published-date guard (top-K).
    as_of = await extraction.enrich(results, top_k=top_k, want_content=want_content)
    if drop_stale:
        results = [r for r in results if not r.stale]

    # [6] Rerank + dedup.
    results = await rerank.rerank_and_dedup(query, results)

    # [7] Output contract.
    resp = SearchResponse(query=query, results=results, as_of=as_of,
                          providers_used=providers_used, cost_units=cost_units,
                          from_cache=False)

    fresh_covered = cls["fresh"] and any(
        r.published_at and (as_of is None or r.published_at >= as_of - 7 * 86400)
        for r in results
    )
    obs.record_query(from_cache=False, cost_units=cost_units, fresh=cls["fresh"],
                     fresh_covered=fresh_covered)

    if use_cache and results:
        await cache.put(key, norm, resp, ttl)
    return resp
