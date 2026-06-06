"""DuckDuckGo provider (Part 2 zero-cost fallback).

No key, no quota. DDG aggressively rate-limits automated access and answers with
a 202 "anomaly" challenge under bursts, so this provider is best-effort: it
retries with backoff + UA rotation and tries multiple endpoints/parse shapes.
For dependable, high-volume real-time search, configure Tavily (primary) — DDG is
the keep-the-lights-on fallback. DDG exposes no publish dates, so published_at is
filled in later by the freshness guard (page-metadata extraction).
"""
from __future__ import annotations

import asyncio
import random
import re
from html import unescape
from urllib.parse import unquote

from ... import http_client
from ..base import SearchProvider
from ..schema import SearchResult

_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]
_ENDPOINTS = ["https://html.duckduckgo.com/html/", "https://duckduckgo.com/html/"]


def _clean(t: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", t or ""))).strip()


def _unwrap(href: str) -> str:
    m = re.search(r"uddg=([^&]+)", href)
    return unquote(m.group(1)) if m else href


def _parse(html: str, max_results: int) -> list[SearchResult]:
    out: list[SearchResult] = []
    # Anchor-based parse (robust to layout shifts); snippet matched nearby.
    for m in re.finditer(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                         html, flags=re.DOTALL | re.IGNORECASE):
        url = _unwrap(unescape(m.group(1)).strip())
        title = _clean(m.group(2))
        tail = html[m.end():m.end() + 1200]
        sm = re.search(r'class="result__snippet"[^>]*>(.*?)</(?:a|div)>', tail,
                       flags=re.DOTALL | re.IGNORECASE)
        snippet = _clean(sm.group(1)) if sm else ""
        if url.startswith("http") and title:
            out.append(SearchResult(title=title, url=url, snippet=snippet,
                                    source_provider="duckduckgo"))
        if len(out) >= max_results:
            break
    return out


def _is_challenge(text: str) -> bool:
    low = text.lower()
    return "anomaly" in low or "challenge" in low


class DuckDuckGoProvider(SearchProvider):
    name = "duckduckgo"
    cost_per_call = 0
    supports_recency = False
    max_retries = 3

    async def search(self, query, *, max_results=8, recency=None, is_news=False,
                     include_raw_content=False) -> list[SearchResult]:
        df = {"day": "d", "week": "w", "month": "m"}.get(recency or "")
        data = {"q": query, "kl": "us-en"}
        if df:
            data["df"] = df

        for attempt in range(self.max_retries):
            endpoint = _ENDPOINTS[attempt % len(_ENDPOINTS)]
            ua = _UAS[attempt % len(_UAS)]
            try:
                resp = await http_client.client().post(
                    endpoint, data=data,
                    headers={"User-Agent": ua, "Accept-Language": "en-US,en;q=0.9",
                             "Referer": "https://duckduckgo.com/"},
                    timeout=12, follow_redirects=True,
                )
            except Exception:
                await asyncio.sleep(0.4 * (attempt + 1) + random.random() * 0.3)
                continue
            if resp.status_code == 200 and not _is_challenge(resp.text):
                res = _parse(resp.text, max_results)
                if res:
                    return res
            # challenged / empty → back off and retry
            await asyncio.sleep(0.6 * (attempt + 1) + random.random() * 0.4)
        return []
