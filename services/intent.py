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


# ── Memory relevance gate (retrieval gating) ──────────────────────────────────
# True  = clearly wants personal memory context
# False = clearly doesn't (pure technical/factual query, no personal signal)
# None  = ambiguous → caller injects memory by default

_MEM_WANT = re.compile(
    r"\b(remember|recall|you know|told you|mentioned|last time|earlier you|"
    r"we (discussed|decided)|based on what you know|about me|for me|"
    r"should i|recommend|suggest|my (project|name|setup|stack|goal|plan|"
    r"preference|workflow|code|notes?|docs?))\b",
    re.I,
)
_PERSONAL = re.compile(
    r"\b(i|i'm|i've|i'd|i'll|me|my|mine|myself|we|we're|our|us)\b", re.I
)
_MEM_SKIP = re.compile(
    r"^\s*(what(?:'s| is| are)|who (?:is|was)|define|explain|how (?:do|does|to)|"
    r"write (?:me )?(?:a |an |the )?(?:function|code|script|program|regex|sql|query|"
    r"class|component)|generate|translate|summari[sz]e this|fix this|give me an example)\b",
    re.I,
)


def memory_relevance(text: str):
    """Return True (wants memory), False (skip memory), or None (ambiguous).

    False is returned only when the message is clearly impersonal: a definition,
    code-generation, or technical explanation request with no first-person signal.
    None and True both result in memory injection; False skips it (except pinned atoms).

    Retained for backward-compat (other callers + tests). The chat hot-path now
    uses the richer cognitive-mode gate below (retrieval_mode / classify_mode).
    """
    t = (text or "").strip()
    if not t:
        return False
    if _MEM_WANT.search(t):
        return True
    if _MEM_SKIP.match(t) and not _PERSONAL.search(t):
        return False
    return None


# ── W1: cognitive-mode retrieval gate ─────────────────────────────────────────
# The headline fix. Before retrieve() fires, classify what the user is actually
# *doing*, then retrieve only what serves that cognitive mode. Stage 1 is pure
# regex/heuristic (~0ms, hot-path safe). Stage 2 is an optional cheap-model
# escalation for the ambiguous residual ("factual"), wired in chat.py but OFF by
# default so the common path never pays a model round-trip (cost→latency→intel).
#
# Modes (see spec W1 §4):
#   tool        — deterministic local answer; retrieve nothing.
#   no_context  — generic world-knowledge / generation, no personal signal;
#                 suppress ambient memory, keep document RAG.
#   factual     — specific (possibly personal) fact lookup; tight, high-precision.
#   technical   — code / debugging; docs + technical atoms, suppress personal.
#   exploratory — brainstorming; wider, more associative retrieval.
#   personal    — reflection or explicit memory request; full memory injection.
#
# Pinned atoms and explicitly-scoped project/document context are NEVER suppressed
# by this gate — that protection lives in retrieval.retrieve() and chat.py, not
# here. This function only chooses a mode.
RETRIEVAL_MODES = ("tool", "no_context", "factual", "technical", "exploratory", "personal")

# Per-mode retrieval policy (consumed by retrieval.retrieve via retrieval.policy_for).
# Lives here so it stays importable without the heavy retrieval deps (numpy etc.),
# which keeps the W1 suppression invariants unit-testable. Defaults lean toward
# PRECISION — the observed problem is over-fetching. Every value is [VALIDATE]
# against scripts/bench.py + the labelled query set and is overridable at runtime
# via the app_config JSON key "retrieval.mode_policies".
#
#   inject_memory     — run the ambient memory KNN/FTS at all (pinned atoms are
#                       ALWAYS included regardless; this only gates AMBIENT recall).
#   inject_docs       — run document RAG.
#   k                 — memory candidate count.
#   min_cos           — cosine floor for an ambient memory atom to count.
#   budget_tokens     — memory+doc block token budget for this mode.
#   suppress_personal — drop personal-flavoured atoms (opinion/desire/trait/
#                       self_perception) so technical queries don't pull life facts.
MODE_POLICIES: dict[str, dict] = {
    "tool": {
        "inject_memory": False, "inject_docs": False, "k": 0,
        "min_cos": 0.99, "budget_tokens": 0, "suppress_personal": False,
    },
    "no_context": {
        "inject_memory": False, "inject_docs": True, "k": 0,
        "min_cos": 0.99, "budget_tokens": 350, "suppress_personal": False,
    },
    "factual": {
        "inject_memory": True, "inject_docs": True, "k": 6,
        "min_cos": 0.42, "budget_tokens": 350, "suppress_personal": False,
    },
    "technical": {
        "inject_memory": True, "inject_docs": True, "k": 8,
        "min_cos": 0.38, "budget_tokens": 500, "suppress_personal": True,
    },
    "exploratory": {
        "inject_memory": True, "inject_docs": True, "k": 14,
        "min_cos": 0.28, "budget_tokens": 700, "suppress_personal": False,
    },
    "personal": {
        "inject_memory": True, "inject_docs": True, "k": 14,
        "min_cos": 0.25, "budget_tokens": 700, "suppress_personal": False,
    },
}

# Technical / debugging signals (code, errors, tooling). [VALIDATE]
_TECH_SIGNALS = re.compile(
    r"```|\b(def |class |import |func |const |let |var |return |async |await |"
    r"stack\s*trace|traceback|exception|stacktrace|null\s*pointer|segfault|"
    r"compile[rd]?|runtime\s+error|type\s*error|syntax\s*error|undefined|"
    r"regex|regexp|sql\b|query|schema|endpoint|api\b|payload|"
    r"npm|pip|pytest|docker|kubernetes|kubectl|git\b|webpack|"
    r"bug|debug|refactor|stack\s+overflow|deadlock|race\s+condition|"
    r"python|javascript|typescript|rust|golang|c\+\+|java\b|sqlite|postgres|redis)\b",
    re.I,
)
_TECH_ERROR = re.compile(r"\b(error|exception|fail(?:ing|ed|s)?|crash(?:ing|ed|es)?|broke[n]?|"
                         r"not\s+work(?:ing)?|won'?t\s+\w+|can'?t\s+\w+)\b", re.I)

# Exploratory / brainstorming signals. [VALIDATE]
_EXPLORE_SIGNALS = re.compile(
    r"\b(brainstorm|ideas?\s+for|some\s+ideas|what\s+if|explore|options?\b|"
    r"ways?\s+to|help\s+me\s+think|think\s+through|thoughts?\s+on|"
    r"pros\s+and\s+cons|trade.?offs?|approach(?:es)?|alternatives?|"
    r"how\s+(?:should|could|might)\s+i|what\s+(?:should|could)\s+i|"
    r"brainstorming|riff\s+on|what\s+are\s+some)\b",
    re.I,
)


def retrieval_mode(text: str, intent: "Intent | None" = None) -> str:
    """Stage-1 (regex/heuristic) cognitive-mode classification. ~0ms.

    Returns one of RETRIEVAL_MODES. The default for the ambiguous residual is
    "factual" (tight, high-precision retrieval) — precision over recall, because
    the observed problem is over-fetching. Callers may escalate "factual" to a
    cheap-model pass (classify_mode, escalation gated by config).
    """
    t = (text or "").strip()
    if not t:
        return "no_context"

    intent = intent if intent is not None else classify(t)

    # 1. tool — deterministic local answer; nothing to retrieve.
    if (intent.time_query or intent.math_expr or intent.unit_conv
            or intent.stock_ticker or intent.weather_loc is not None
            or intent.is_bare_local):
        return "tool"

    # 2. personal — explicit memory request or self-reflection.
    if _MEM_WANT.search(t):
        return "personal"

    has_personal = bool(_PERSONAL.search(t))
    is_skip = bool(_MEM_SKIP.match(t))

    # 3. no_context — generic definition / generation / explanation with no
    #    first-person signal. Beats technical so "explain how async works" gets
    #    zero personal memory, not just personal-suppressed.
    if is_skip and not has_personal:
        return "no_context"

    # 4. technical — code / debugging context.
    if _TECH_SIGNALS.search(t) or (_TECH_ERROR.search(t) and has_personal):
        return "technical"

    # 5. exploratory — brainstorming / open-ended thinking.
    if _EXPLORE_SIGNALS.search(t):
        return "exploratory"

    # 6. factual — tight, high-precision default (ambiguous residual).
    return "factual"


_MODE_LLM_SYSTEM = (
    "Classify the user's message into ONE retrieval mode. Reply with ONLY the "
    "single lowercase word, nothing else.\n"
    "Modes:\n"
    "- no_context: generic world-knowledge / code-gen / definition needing none "
    "of the user's personal data.\n"
    "- factual: a specific fact lookup that may depend on the user's own data.\n"
    "- technical: debugging / code where prior technical context helps but "
    "personal life details do not.\n"
    "- exploratory: brainstorming / open-ended thinking that benefits from "
    "broad, associative recall.\n"
    "- personal: reflection about the user, or an explicit request to use what "
    "you remember about them."
)


async def classify_mode(text: str, intent: "Intent | None" = None,
                        escalate=None) -> str:
    """Two-stage mode classification.

    Stage 1 is always the regex pass. When `escalate` is provided (an async
    callable taking messages -> str, e.g. llm.cheap) AND the regex result is the
    ambiguous "factual" residual, escalate to the cheap model to refine. Any
    failure or unrecognised reply falls back to the regex result — the gate must
    never block a reply (hot-path rule 1).
    """
    mode = retrieval_mode(text, intent)
    if escalate is None or mode != "factual":
        return mode
    try:
        raw = await escalate(
            [{"role": "system", "content": _MODE_LLM_SYSTEM},
             {"role": "user", "content": (text or "")[:600]}]
        )
        guess = (raw or "").strip().lower().split()[0] if raw else ""
        if guess in RETRIEVAL_MODES and guess != "tool":
            return guess
    except Exception:
        pass
    return mode
