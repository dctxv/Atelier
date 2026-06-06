"""Monthly provider-quota tracking (Part 3 cost rules / Part 5 F2).

Counts provider calls vs free-tier caps. When a provider is at/over its cap the
router skips it and falls back to a free provider, so a free-tier cap is never
silently exceeded. Surfaced in /api/metrics.
"""
from __future__ import annotations

import time

from .. import db

# Free-tier monthly caps. 0 = unlimited (self-hosted / scrape); None = no free tier.
FREE_CAPS = {
    "tavily": 1000,
    "brave": None,       # paid only
    "searxng": 0,        # self-hosted, unlimited
    "duckduckgo": 0,     # scrape, unlimited (be polite)
}


def _month() -> str:
    return time.strftime("%Y-%m", time.gmtime())


async def record(provider: str, *, error: bool = False):
    month = _month()
    await db.execute(
        "INSERT INTO search_provider_usage(provider, month, calls, errors) VALUES(?,?,1,?) "
        "ON CONFLICT(provider, month) DO UPDATE SET calls=calls+1, errors=errors+?",
        (provider, month, 1 if error else 0, 1 if error else 0),
    )


async def calls_this_month(provider: str) -> int:
    row = await db.fetchone(
        "SELECT calls FROM search_provider_usage WHERE provider=? AND month=?",
        (provider, _month()),
    )
    return row["calls"] if row else 0


async def over_quota(provider: str) -> bool:
    cap = FREE_CAPS.get(provider, 0)
    if cap in (0, None):
        # 0 = unlimited free; None = paid (no free cap to exceed) — let it run.
        return False
    return await calls_this_month(provider) >= cap


async def remaining(provider: str) -> int | None:
    cap = FREE_CAPS.get(provider)
    if cap in (0, None):
        return None
    return max(0, cap - await calls_this_month(provider))


async def summary() -> dict:
    rows = await db.fetchall(
        "SELECT provider, calls, errors FROM search_provider_usage WHERE month=?", (_month(),)
    )
    out = {}
    for r in rows:
        out[r["provider"]] = {
            "calls": r["calls"], "errors": r["errors"],
            "cap": FREE_CAPS.get(r["provider"]),
            "remaining": await remaining(r["provider"]),
        }
    return out
