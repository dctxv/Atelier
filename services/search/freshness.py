"""Freshness classifier (Part 5 D1) — local, rules-based, < 30ms.

Decides whether a query is time-sensitive, what recency window it wants, and
whether it should route to news. Rules (not a model) so it's instant and free
and adds nothing to the hot path. Output drives both the provider recency params
(D2) and the volatility-aware cache TTL (D3).
"""
from __future__ import annotations

import re

# Strong "right now / most recent" signals -> day window, news routing.
_NOW = re.compile(
    r"\b(today|tonight|right now|just now|breaking|latest|newest|most recent|"
    r"recent(ly)?|currently|current|live|"
    r"this (morning|afternoon|evening|week)|as of|update[sd]?|"
    r"in \d{4}|this year|right now|up.?to.?date)\b", re.I)
# Volatile data that changes by the minute/hour.
_VOLATILE = re.compile(
    r"\b(price|stock|score|weather|forecast|traffic|election|results?|"
    r"who won|standings|exchange rate|crypto|bitcoin|ethereum)\b", re.I)
# News-y nouns / event verbs.
_NEWS = re.compile(r"\b(news|announce[ds]?|release[ds]?|launch(ed|es)?|outage|"
                   r"earthquake|storm|incident|died|dies|wins?|won|"
                   r"strikes?|attack(s|ed)?|ceasefire|war|clash(es)?|killed|"
                   r"crash(es|ed)?|resign(s|ed)?|quits?|verdict|ruling|"
                   r"summit|protest(s)?|recall|merger|acquisition)\b", re.I)
# Year/recent-date mentions (this year or explicit recent year).
_YEAR = re.compile(r"\b(20[2-9]\d)\b")

# TTLs (seconds): volatile/news short, stable long.
TTL_VOLATILE = 5 * 60
TTL_NEWS = 15 * 60
TTL_RECENT = 60 * 60
TTL_STABLE = 24 * 3600


def classify(query: str) -> dict:
    q = query or ""
    now = bool(_NOW.search(q))
    volatile = bool(_VOLATILE.search(q))
    newsy = bool(_NEWS.search(q)) or now
    has_year = bool(_YEAR.search(q))

    if volatile or now:
        window = "day"
    elif newsy or has_year:
        window = "week"
    else:
        window = "none"

    fresh = window != "none"
    is_news = newsy and fresh
    return {"fresh": fresh, "window": window, "is_news": is_news, "volatile": volatile}


def recency_param(cls: dict) -> str | None:
    w = cls.get("window")
    return w if w in ("day", "week", "month") else None


def ttl_for(cls: dict) -> int:
    if cls.get("volatile"):
        return TTL_VOLATILE
    if cls.get("is_news"):
        return TTL_NEWS
    if cls.get("fresh"):
        return TTL_RECENT
    return TTL_STABLE
