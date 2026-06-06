"""Content extraction + stale-link / published-date guard (Part 5 E1 + D4).

These share page fetches, so they live together. For top-K results we fetch the
page once and derive three things:
  - clean content (when the provider didn't supply raw_content)
  - published_at (from page metadata — vital when a provider like DDG gives no
    dates; this is what makes the real-time gate pass on free providers)
  - a stale flag (dead/404/empty links — Tavily can serve stale cache links)

Jina Reader (free) is the fallback extractor for SPA / JS-heavy pages where a
plain fetch yields too little text. Fetches run in parallel, capped by top_k.
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from html import unescape

from .. import db, http_client
from .schema import SearchResult

_UA = "Mozilla/5.0 (compatible; AtelierSearch/1.0; +local)"
MIN_USEFUL_CHARS = 200
MAX_CONTENT_CHARS = 8000


def _parse_iso(value: str) -> int | None:
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except Exception:
        try:
            return int(datetime.strptime(value[:10], "%Y-%m-%d")
                       .replace(tzinfo=timezone.utc).timestamp())
        except Exception:
            return None


def _extract_date(html: str) -> int | None:
    patterns = [
        r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+name=["\']article:published_time["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+property=["\']og:updated_time["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+name=["\'](?:date|pubdate|publishdate|dc\.date)["\'][^>]+content=["\']([^"\']+)',
        r'<time[^>]+datetime=["\']([^"\']+)',
    ]
    for p in patterns:
        m = re.search(p, html, re.I)
        if m:
            d = _parse_iso(m.group(1).strip())
            if d:
                return d
    # JSON-LD datePublished
    for m in re.finditer(r'"datePublished"\s*:\s*"([^"]+)"', html, re.I):
        d = _parse_iso(m.group(1).strip())
        if d:
            return d
    return None


def _strip(html: str) -> str:
    html = re.sub(r"<(script|style|nav|footer|header|aside)[^>]*>.*?</\1>", " ",
                  html, flags=re.DOTALL | re.IGNORECASE)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()


async def _jina(url: str) -> str:
    try:
        r = await http_client.client().get(f"https://r.jina.ai/{url}", timeout=15,
                                           headers={"User-Agent": _UA})
        if r.status_code == 200:
            return r.text[:MAX_CONTENT_CHARS]
    except Exception:
        pass
    return ""


async def fetch_page(url: str, *, want_content: bool = True) -> dict:
    """Fetch one page. Returns {ok, status, content, published_at}."""
    try:
        r = await http_client.client().get(url, timeout=12, follow_redirects=True,
                                           headers={"User-Agent": _UA})
        status = r.status_code
        if status >= 400:
            return {"ok": False, "status": status, "content": "", "published_at": None}
        html = r.text
        published = _extract_date(html)
        content = ""
        if want_content:
            content = _strip(html)[:MAX_CONTENT_CHARS]
            if len(content) < MIN_USEFUL_CHARS:  # SPA / JS page → Jina fallback
                jina = await _jina(url)
                if len(jina) > len(content):
                    content = jina
        return {"ok": True, "status": status, "content": content, "published_at": published}
    except Exception:
        return {"ok": False, "status": 0, "content": "", "published_at": None}


async def enrich(results: list[SearchResult], *, top_k: int, want_content: bool) -> int | None:
    """Enrich top_k results with content/published_at, flag stale ones.

    Returns as_of (max published_at seen, or now if any fresh content)."""
    targets = results[:top_k]

    async def one(res: SearchResult):
        need_content = want_content and not res.content
        need_date = res.published_at is None
        if not need_content and not need_date:
            return
        info = await fetch_page(res.url, want_content=need_content)
        if not info["ok"]:
            res.stale = True
            return
        if need_content and info["content"]:
            res.content = info["content"]
        if need_date and info["published_at"]:
            res.published_at = info["published_at"]

    await asyncio.gather(*(one(r) for r in targets))

    dates = [r.published_at for r in results if r.published_at]
    if dates:
        return max(dates)
    return db.now()
