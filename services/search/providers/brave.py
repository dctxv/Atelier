"""Brave Search provider (Part 2 optional paid upgrade).

Independent index, lowest measured latency, Brave News for minute-level recency.
No free tier, so it's off unless a key is configured. Same interface as the rest.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ... import config, http_client
from ..base import SearchProvider
from ..schema import SearchResult

_FRESHNESS = {"day": "pd", "week": "pw", "month": "pm"}


def _parse_date(value) -> int | None:
    if not value:
        return None
    try:
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())
    except Exception:
        return None


class BraveProvider(SearchProvider):
    name = "brave"
    cost_per_call = 1
    supports_recency = True

    async def available(self) -> bool:
        return await config.has_secret("brave_api_key")

    async def search(self, query, *, max_results=8, recency=None, is_news=False,
                     include_raw_content=False) -> list[SearchResult]:
        key = await config.get_secret("brave_api_key")
        if not key:
            raise RuntimeError("Brave API key not configured")
        params = {"q": query, "count": max(1, min(max_results, 20))}
        if recency in _FRESHNESS:
            params["freshness"] = _FRESHNESS[recency]
        headers = {"Accept": "application/json", "X-Subscription-Token": key}
        endpoint = ("https://api.search.brave.com/res/v1/news/search" if is_news
                    else "https://api.search.brave.com/res/v1/web/search")
        resp = await http_client.client().get(endpoint, params=params, headers=headers, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        items = (data.get("news", {}) if is_news else data.get("web", {})).get("results", [])
        out = []
        for r in items:
            out.append(SearchResult(
                title=_clean(r.get("title")),
                url=(r.get("url") or "").strip(),
                snippet=_clean(r.get("description")),
                published_at=_parse_date(r.get("age") or r.get("page_age")),
                source_provider=self.name,
            ))
        return out


def _clean(t):
    import re
    from html import unescape
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", t or ""))).strip()
