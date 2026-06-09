"""Single-pass intent classifier for the chat turn.

Replaces the four independent sequential regex probes in routers/chat.py
with one typed pass that returns an Intent dataclass. Stage 1 is pure regex
(~0ms). Stage 2 would be a cheap-model fallback for ambiguous cases — not
yet wired, but the structure is ready.

Mis-fire fixes vs. the old code:
  stock:   require $TICKER cashtag OR explicit "stock/share price of TICKER"
           with a short English-word stoplist to reject false positives.
  weather: bounded location capture; >4 words → None (model handles it).
  math:    require an operator or unit token in addition to digits, so
           "plan 9" and "section 4" don't parse.
  time:    guard against advice queries ("what time should I sleep").
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── English words that look like tickers but aren't ──────────────────────────
_TICKER_STOPLIST = {
    "A", "I", "IT", "IS", "AM", "BE", "DO", "GO", "IN", "ON", "UP", "OR",
    "AT", "BY", "TO", "VS", "OK", "SO", "NO", "MY", "TV", "US", "UK", "EU",
    "AI", "ML", "CEO", "CTO", "CFO", "COO", "HR", "PR", "IP", "ID", "PI",
}

# ── Stock: cashtag OR explicit "stock/share price of TICKER" ─────────────────
_STOCK_CASHTAG = re.compile(r"\$([A-Z]{1,5})\b")
_STOCK_EXPLICIT = re.compile(
    r"\b(?:stock|share)\s+(?:price\s+)?(?:of|for)\s+([A-Z]{2,5})\b", re.I
)

# ── Weather: bounded location ─────────────────────────────────────────────────
_WEATHER_Q = re.compile(
    r"\b(?:weather|temperature|forecast|how\s+(?:hot|cold)\s+is\s+it)\b"
    r"(?:\s+(?:in|for|at))?\s+([A-Za-z][A-Za-z\s,]{0,30}?)(?:\?|$|\.)",
    re.I,
)
# Simpler trigger (used when above doesn't capture a location)
_WEATHER_TRIGGER = re.compile(
    r"\b(?:weather|temperature|forecast|how\s+(?:hot|cold)\s+is\s+it)\b", re.I
)

# ── Math: must have operator/function/unit in addition to a digit ─────────────
_MATH_OPERATOR = re.compile(r"[+\-*/^%()]|sqrt|sin|cos|tan|log|exp|\d+\s*\*\*\s*\d+")
_HAS_DIGIT = re.compile(r"\d")

# ── Unit conversion: "X unit to unit" ────────────────────────────────────────
_UNIT_CONV = re.compile(
    r"(\d[\d\.\s]*[a-zA-Z_]+(?:[\s*/]+[a-zA-Z_]+)*)\s+(?:to|in)\s+([a-zA-Z_]+(?:[\s*/]+[a-zA-Z_]+)*)",
    re.I,
)

# ── Time: must be asking for the CURRENT time, not using "time" as a noun ────
_TIME_Q = re.compile(
    r"\b(?:what(?:'?s|\s+is)\s+(?:the\s+)?(?:current\s+)?time"
    r"|current\s+time"
    r"|time\s+(?:now|in|at)"
    r"|what\s+time\s+is\s+it"
    r"|clock\s+in"
    r"|(?:today'?s?\s+)?date\s+(?:today|now|in)"
    r"|what'?s?\s+today'?s?\s+date)\b",
    re.I,
)
# Guard: these are advice/noun uses of "time" — do NOT fire clock card
_TIME_ADVICE = re.compile(
    r"\b(?:what\s+time\s+(?:should|do|to|can|will|would)|"
    r"best\s+time|good\s+time|right\s+time|time\s+to\s+(?:go|sleep|eat|work|start))\b",
    re.I,
)

# ── Timezone abbreviations ────────────────────────────────────────────────────
_TZ_ABBREVS: dict[str, str] = {
    "aest": "Australia/Sydney",
    "aedt": "Australia/Sydney",
    "acst": "Australia/Darwin",
    "awst": "Australia/Perth",
    "nzst": "Pacific/Auckland",
    "nzdt": "Pacific/Auckland",
    "jst":  "Asia/Tokyo",
    "cst":  "America/Chicago",
    "est":  "America/New_York",
    "pst":  "America/Los_Angeles",
    "gmt":  "UTC",
    "bst":  "Europe/London",
    "ist":  "Asia/Kolkata",
    "sgt":  "Asia/Singapore",
}

# ── Web search signals ────────────────────────────────────────────────────────
_SEARCH_SIGNALS = re.compile(
    r"\b(?:today|tonight|right\s+now|just\s+now|breaking|latest|current(?:ly)?|"
    r"live|update[sd]?|recent(?:ly)?|newest|most\s+recent|up.?to.?date|"
    r"this\s+(?:morning|week|month|year)|as\s+of|in\s+\d{4}|this\s+year|"
    r"news|score[sd]?|standings?|results?|"
    r"who\s+(?:won|is\s+winning)|announce[ds]?|launch(?:ed)?|release[ds]?|"
    r"died?|killed|attack(?:ed)?|strike[sd]?|election|forecast|"
    r"how\s+(?:do|does|to)|explain|definition|meaning\s+of|vs\.?|"
    r"compare|review|recommend|best|top\s+\d|20[2-9]\d|"
    r"is\s+(?:the\s+)?\w+\s+(?:the\s+)?latest|who\s+(?:runs|leads|owns|is)\s+\w+)\b",
    re.I,
)

# ── Chat-only: short conversational messages ──────────────────────────────────
_CHAT_ONLY = re.compile(
    r"^(?:hey|hi+|hello|sup|yo|thanks?|thank\s+you|ok(?:ay)?|sure|cool|got\s+it|"
    r"nice|great|lol|haha|wow|yes|no|nope|yep|please|sorry|excuse\s+me|"
    r"good\s+(?:morning|night|evening|day)|how\s+are\s+you|what'?s\s+up|"
    r"sounds\s+good|perfect|awesome|exactly|right|understood|noted)[!?.,\s]*$",
    re.I,
)

# ── Web difficulty signals ────────────────────────────────────────────────────
_HARD_SIGNALS = re.compile(
    r"\b(?:vs\.?|compare|comparison|versus|difference\s+between|"
    r"better|best\s+for|which\s+is\s+better|pros\s+and\s+cons|"
    r"recommend|alternative|top\s+\d|ranked|ranking)\b",
    re.I,
)
_MODERATE_SIGNALS = re.compile(
    r"\b(?:latest|recent|current|now|today|this\s+week|this\s+year|"
    r"how\s+does|why\s+is|explain|what\s+is|breaking)\b",
    re.I,
)


@dataclass
class Intent:
    needs_web: bool = False
    web_difficulty: str = "none"          # "none"|"simple"|"moderate"|"hard"
    math_expr: str | None = None          # cleaned expression if math detected
    unit_conv: tuple | None = None        # (from_str, to_str) for unit conversion
    time_query: bool = False
    tz_abbrev: str | None = None          # resolved IANA zone from abbreviation
    weather_loc: str | None = None        # location string or None
    stock_ticker: str | None = None       # ticker symbol or None
    is_chat_only: bool = False
    is_bare_local: bool = False           # True → card candidate (no LLM needed)


def classify(text: str) -> Intent:
    """Classify a user message into a typed Intent. Pure regex, ~0ms."""
    t = (text or "").strip()
    if not t:
        return Intent()

    # ── Chat-only short-circuit ───────────────────────────────────────────────
    if _CHAT_ONLY.match(t) or len(t) < 4:
        return Intent(is_chat_only=True)

    intent = Intent()

    # ── Time query ────────────────────────────────────────────────────────────
    if _TIME_Q.search(t) and not _TIME_ADVICE.search(t):
        intent.time_query = True
        # Check for timezone abbreviations
        tl = t.lower()
        for abbr, zone in _TZ_ABBREVS.items():
            if re.search(rf"\b{abbr}\b", tl):
                intent.tz_abbrev = zone
                break
        intent.is_bare_local = True
        return intent  # time query is always answered by clock card; stop here

    # ── Stock ─────────────────────────────────────────────────────────────────
    cashtag = _STOCK_CASHTAG.search(t)
    if cashtag:
        ticker = cashtag.group(1)
        if ticker not in _TICKER_STOPLIST:
            intent.stock_ticker = ticker
    if not intent.stock_ticker:
        explicit = _STOCK_EXPLICIT.search(t)
        if explicit:
            ticker = explicit.group(1).upper()
            if ticker not in _TICKER_STOPLIST:
                intent.stock_ticker = ticker

    # ── Weather ───────────────────────────────────────────────────────────────
    if not intent.stock_ticker:  # stock + weather are mutually exclusive
        wm = _WEATHER_Q.search(t)
        if wm:
            loc = wm.group(1).strip().rstrip("?,.")
            # Reject if location looks like a sentence fragment (>4 words)
            if loc and len(loc.split()) <= 4:
                intent.weather_loc = loc
        elif _WEATHER_TRIGGER.search(t):
            intent.weather_loc = ""  # trigger without location — model extracts

    # ── Unit conversion (no arithmetic operator required: "100 km to miles") ──
    unit_m = _UNIT_CONV.search(t) if _HAS_DIGIT.search(t) else None
    if unit_m:
        intent.unit_conv = (unit_m.group(1).strip(), unit_m.group(2).strip())

    # ── Generic math expression (requires an operator) ────────────────────────
    if not intent.unit_conv and _HAS_DIGIT.search(t) and _MATH_OPERATOR.search(t):
        expr = re.sub(
            r"^(?:what(?:'?s|\s+is)\s+)?(?:calculate|compute|solve|find)?\s*",
            "", t, flags=re.I
        ).strip().rstrip("?.")
        intent.math_expr = expr if expr else None

    # ── Web search ────────────────────────────────────────────────────────────
    if not intent.time_query:
        # Don't search if the message has a deterministic local answer
        has_local = bool(intent.stock_ticker or intent.weather_loc is not None
                         or intent.math_expr or intent.unit_conv)

        if _SEARCH_SIGNALS.search(t):
            intent.needs_web = True
            # Score difficulty
            if _HARD_SIGNALS.search(t):
                intent.web_difficulty = "hard"
            elif _MODERATE_SIGNALS.search(t) or len(t.split()) > 12:
                intent.web_difficulty = "moderate"
            else:
                intent.web_difficulty = "simple"
        elif not has_local and len(t) >= 6:
            # Entity-recency fallback: if a proper noun or year present, moderate
            if re.search(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", t):
                # Multi-word proper noun → might need freshness
                intent.needs_web = True
                intent.web_difficulty = "moderate"

    # ── Bare local query (card candidate) ────────────────────────────────────
    if not intent.needs_web:
        local_triggers = [intent.stock_ticker, intent.weather_loc,
                          intent.math_expr, intent.unit_conv]
        n_local = sum(1 for x in local_triggers if x is not None)
        if n_local == 1:
            # Strip the matched expression; if only scaffolding remains → bare
            remainder = t
            if intent.math_expr:
                remainder = t.replace(intent.math_expr, "")
            elif intent.unit_conv and unit_m:
                remainder = t[:unit_m.start()] + t[unit_m.end():]
            elif intent.stock_ticker:
                remainder = re.sub(
                    rf"\${re.escape(intent.stock_ticker)}\b|"
                    rf"\b{re.escape(intent.stock_ticker)}\b", "", t, flags=re.I)
            elif intent.weather_loc:
                remainder = t.replace(intent.weather_loc, "")

            scaffolding = re.sub(
                r"\b(?:what(?:'?s|\s+is)?|how\s+much|tell\s+me|show|get|give\s+me|"
                r"can\s+you|please|the|is|of|for|convert|calculate|compute)\b",
                "", remainder, flags=re.I
            )
            intent.is_bare_local = len(scaffolding.strip().strip("?.,!")) < 5

    return intent
