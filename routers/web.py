"""Web search endpoint (used by the chat web-search toggle)."""
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
    return [{
        "title": f"System time ({zone})",
        "url": "local://system-clock",
        "content": f"{now.strftime('%A, %d %B %Y %H:%M:%S %Z')} (ISO: {now.isoformat()}).",
    }]


@router.post("/web-search")
async def web_search(request: Request):
    data = await request.json()
    query = (data.get("query") or "").strip()
    result = await search.search(query)
    if result.get("ok"):
        return result
    fallback = _time_fallback(query)
    if fallback:
        return {"ok": True, "provider": "local-time", "results": fallback}
    return result
