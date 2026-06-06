"""Tavily provider (Part 2 primary).

LLM-native: one round-trip returns scored results plus optional raw_content.
Real-time via topic=news + time_range/days. Default search_depth=basic for low
latency (advanced is 5s+ and only justified on explicit deep requests, which are
a downstream concern, not this layer's default).

Key is stored encrypted (config.get_secret); never plaintext.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ... import config, http_client
from ..base import SearchProvider
from ..schema import SearchResult

_TIME_RANGE = {"day": "day", "week": "week", "month": "month"}


def _parse_date(value) -> int | None:
    if not value:
        return None
    try:
        s = str(value).replace("Z", "+00:00")
        return int(datetime.fromisoformat(s).timestamp())
    except Exception:
        try:
            return int(datetime.strptime(str(value)[:10], "%Y-%m-%d")
                       .replace(tzinfo=timezone.utc).timestamp())
        except Exception:
            return None


class TavilyProvider(SearchProvider):
    name = "tavily"
    cost_per_call = 1
    supports_recency = True

    async def available(self) -> bool:
        return await config.has_secret("tavily_api_key")

    async def search(self, query, *, max_results=8, recency=None, is_news=False,
                     include_raw_content=False) -> list[SearchResult]:
        key = await config.get_secret("tavily_api_key")
        if not key:
            raise RuntimeError("Tavily API key not configured")

        payload = {
            "api_key": key,
            "query": query,
            "search_depth": "basic",
            "max_results": max(1, min(max_results, 20)),
            "include_raw_content": bool(include_raw_content),
            "include_answer": False,
        }
        if is_news:
            payload["topic"] = "news"
            payload["days"] = {"day": 1, "week": 7, "month": 30}.get(recency, 3)
        elif recency in _TIME_RANGE:
            payload["time_range"] = _TIME_RANGE[recency]

        resp = await http_client.client().post(
            "https://api.tavily.com/search", json=payload, timeout=15
        )
        resp.raise_for_status()
        data = resp.json()

        out = []
        for r in data.get("results", []):
            out.append(SearchResult(
                title=(r.get("title") or "").strip(),
                url=(r.get("url") or "").strip(),
                snippet=(r.get("content") or "").strip(),
                content=(r.get("raw_content") or None),
                published_at=_parse_date(r.get("published_date")),
                score=float(r.get("score") or 0.0),
                source_provider=self.name,
            ))
        return out
