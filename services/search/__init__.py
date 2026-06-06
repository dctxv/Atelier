"""The Atelier web-search layer.

Public API:
  search(query, ...) -> SearchResponse   # the one entry point (sync fast path
                                         # for chat/lookups; also used inside jobs
                                         # for the research pipeline — Part 5 F1)
  fetch_page(url)                         # single-page clean fetch + metadata
  SearchResult, SearchResponse           # the output contract

Sub-modules (the seven layers) are importable for tests and metrics.
"""
from __future__ import annotations

from . import cache, freshness, obs, registry, usage  # noqa: F401
from .extraction import fetch_page  # noqa: F401
from .pipeline import search  # noqa: F401
from .rerank import chunk  # noqa: F401
from .schema import SearchResponse, SearchResult  # noqa: F401


async def metrics_summary() -> dict:
    return {
        "queries": obs.summary(),
        "cache": await cache.stats(),
        "usage": await usage.summary(),
    }
