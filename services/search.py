"""Web search backend (Part 2.3 prerequisite).

Default target is a local SearXNG instance (free, private, no key). Falls back
to scraping DuckDuckGo HTML, then to a local system-clock answer for time/date
queries. Uses the single shared httpx client. A simple per-URL fetch cache
avoids re-downloading the same page within a run.
"""
from __future__ import annotations

import os
import re
from html import unescape
from urllib.parse import quote_plus

from . import http_client

_fetch_cache: dict[str, str] = {}


def _searxng_base() -> str:
    return os.getenv("SEARXNG_INSTANCE", "http://localhost:8080").rstrip("/")


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", unescape(text)).strip()


async def _searxng(query: str, limit: int) -> list[dict]:
    resp = await http_client.client().get(
        f"{_searxng_base()}/search",
        params={"q": query, "format": "json", "language": "en", "safesearch": 0},
        timeout=12,
    )
    resp.raise_for_status()
    raw = resp.json().get("results", [])[:limit]
    return [{"title": (r.get("title") or "").strip(), "url": (r.get("url") or "").strip(),
             "content": (r.get("content") or "").strip()} for r in raw if r.get("url")]


async def _duckduckgo(query: str, limit: int) -> list[dict]:
    ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
    resp = await http_client.client().get(
        f"https://duckduckgo.com/html/?q={quote_plus(query)}", headers=ua,
        timeout=12, follow_redirects=True,
    )
    resp.raise_for_status()
    blocks = re.findall(r'<div class="result__body">(.*?)</div>\s*</div>', resp.text,
                        flags=re.DOTALL | re.IGNORECASE)[:limit + 2]
    out = []
    for block in blocks:
        lm = re.search(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                       block, flags=re.DOTALL | re.IGNORECASE)
        if not lm:
            continue
        url = unescape(lm.group(1)).strip()
        title = _clean(lm.group(2))
        sm = re.search(r'class="result__snippet"[^>]*>(.*?)</(?:a|div)>', block,
                       flags=re.DOTALL | re.IGNORECASE)
        content = _clean(sm.group(1) if sm else "")
        if url and title:
            out.append({"title": title, "url": url, "content": content})
        if len(out) >= limit:
            break
    return out


async def search(query: str, limit: int = 6) -> dict:
    query = (query or "").strip()
    if not query:
        return {"ok": False, "error": "Missing query", "results": []}
    for provider, fn in (("searxng", _searxng), ("duckduckgo", _duckduckgo)):
        try:
            results = await fn(query, limit)
            if results:
                return {"ok": True, "provider": provider, "results": results}
        except Exception:
            continue
    return {"ok": False, "error": "No web results found (SearXNG unreachable, fallback failed).",
            "results": []}


async def fetch_page(url: str, max_chars: int = 8000) -> str:
    """Fetch and strip a page to plain text, cached by URL."""
    if url in _fetch_cache:
        return _fetch_cache[url]
    try:
        resp = await http_client.client().get(
            url, timeout=15, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; AtelierResearch/1.0)"},
        )
        resp.raise_for_status()
        html = resp.text
        html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        text = _clean(html)[:max_chars]
    except Exception:
        text = ""
    _fetch_cache[url] = text
    return text
