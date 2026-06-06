"""SearXNG provider (Part 2 zero-cost fallback).

Self-hosted, free, no key. Supports a time_range param for recency. Base URL
from the SEARXNG_INSTANCE env (default http://localhost:8080).
"""
from __future__ import annotations

import os

from ... import http_client
from ..base import SearchProvider
from ..schema import SearchResult


def _base() -> str:
    return os.getenv("SEARXNG_INSTANCE", "http://localhost:8080").rstrip("/")


class SearxngProvider(SearchProvider):
    name = "searxng"
    cost_per_call = 0
    supports_recency = True

    async def available(self) -> bool:
        try:
            r = await http_client.client().get(_base(), timeout=2)
            return r.status_code < 500
        except Exception:
            return False

    async def search(self, query, *, max_results=8, recency=None, is_news=False,
                     include_raw_content=False) -> list[SearchResult]:
        params = {"q": query, "format": "json", "language": "en", "safesearch": 0}
        if recency in ("day", "week", "month"):
            params["time_range"] = recency
        if is_news:
            params["categories"] = "news"
        resp = await http_client.client().get(f"{_base()}/search", params=params, timeout=12)
        resp.raise_for_status()
        raw = resp.json().get("results", [])[:max_results]
        return [
            SearchResult(
                title=(r.get("title") or "").strip(),
                url=(r.get("url") or "").strip(),
                snippet=(r.get("content") or "").strip(),
                source_provider=self.name,
            )
            for r in raw if r.get("url")
        ]
