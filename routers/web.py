"""Web search endpoints over the search layer.

/api/search    — the full output contract (ranked, fresh, deduped + metadata).
/api/web-search — legacy-compatible shape for the existing chat web toggle.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request

from services import search

router = APIRouter(prefix="/api")

_ZONES = {
    "sydney": "Australia/Sydney", "melbourne": "Australia/Melbourne",
    "brisbane": "Australia/Brisbane", "perth": "Australia/Perth",
    "adelaide": "Australia/Adelaide", "auckland": "Pacific/Auckland",
    "tokyo": "Asia/Tokyo", "london": "Europe/London",
    "new york": "America/New_York", "los angeles": "America/Los_Angeles", "utc": "UTC",
}


def _time_fallback(query: str):
    q = (query or "").lower()
    if not any(k in q for k in ("time", "date", "clock")):
        return []
    zone = next((z for k, z in _ZONES.items() if k in q), "UTC")
    try:
        tz = ZoneInfo(zone)
    except Exception:
        tz, zone = timezone.utc, "UTC"
    now = datetime.now(tz)
    return [{"title": f"System time ({zone})", "url": "local://system-clock",
             "content": f"{now.strftime('%A, %d %B %Y %H:%M:%S %Z')} (ISO: {now.isoformat()})."}]


@router.post("/search")
async def search_endpoint(request: Request):
    data = await request.json()
    query = (data.get("query") or "").strip()
    resp = await search.search(
        query,
        max_results=int(data.get("max_results", 8)),
        top_k=int(data.get("top_k", 4)),
        want_content=bool(data.get("want_content", False)),
        recency=data.get("recency"),
        use_cache=data.get("use_cache", True),
    )
    return resp.to_dict()


@router.post("/web-search")
async def web_search(request: Request):
    data = await request.json()
    query = (data.get("query") or "").strip()
    resp = await search.search(query, max_results=6, top_k=3, want_content=False)
    if resp.results:
        return {
            "ok": True,
            "provider": ",".join(resp.providers_used) or "none",
            "from_cache": resp.from_cache,
            "as_of": resp.as_of,
            "results": [
                {"title": r.title, "url": r.url, "content": r.content or r.snippet,
                 "published_at": r.published_at, "stale": r.stale}
                for r in resp.results
            ],
        }
    fallback = _time_fallback(query)
    if fallback:
        return {"ok": True, "provider": "local-time", "results": fallback}
    return {"ok": False, "error": "No web results found.", "results": []}
