"""Local deterministic tools — card-quality answers with no LLM call.

try_local(text) -> dict | None

Returns a card payload dict if the text is a clean deterministic query,
or None if not handled here. Designed to be called after the intent
classifier confirms `is_bare_local=True` and exactly one local intent
fired (math/unit already handled by math_eval; this covers the extras).

Tools:
  - Date math     ("days until Christmas", "90 days from today", age)
  - Timezone diff ("3pm Sydney in London")
  - Base/number   ("255 in hex", "0xFF to binary", "0b1010 to decimal")
  - Hash/encode   ("sha256 of hello", "base64 encode X", "url-encode Y")
  - Color conv    ("#8A5A34 to rgb", "rgb(138,90,52) to hex")
  - Tip/split     ("split $240 3 ways with 18% tip")
"""
from __future__ import annotations

import base64
import hashlib
import re
import urllib.parse
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# ── Zone dictionary (shared with chat router) ─────────────────────────────────
_ZONES: dict[str, str] = {
    "sydney": "Australia/Sydney", "melbourne": "Australia/Melbourne",
    "brisbane": "Australia/Brisbane", "perth": "Australia/Perth",
    "adelaide": "Australia/Adelaide", "darwin": "Australia/Darwin",
    "hobart": "Australia/Hobart", "auckland": "Pacific/Auckland",
    "tokyo": "Asia/Tokyo", "london": "Europe/London",
    "new york": "America/New_York", "los angeles": "America/Los_Angeles",
    "chicago": "America/Chicago", "paris": "Europe/Paris",
    "berlin": "Europe/Berlin", "dubai": "Asia/Dubai",
    "singapore": "Asia/Singapore", "hong kong": "Asia/Hong_Kong",
    "utc": "UTC", "mumbai": "Asia/Kolkata", "delhi": "Asia/Kolkata",
    "shanghai": "Asia/Shanghai", "beijing": "Asia/Shanghai",
    "seoul": "Asia/Seoul", "bangkok": "Asia/Bangkok",
    "jakarta": "Asia/Jakarta", "toronto": "America/Toronto",
    "vancouver": "America/Vancouver", "montreal": "America/Toronto",
}


def _find_zone(text: str) -> str | None:
    tl = text.lower()
    # Multi-word cities first (longest match wins)
    for city in sorted(_ZONES, key=len, reverse=True):
        if city in tl:
            return _ZONES[city]
    return None


# ── Date math ────────────────────────────────────────────────────────────────

_DATE_DAYS_UNTIL = re.compile(
    r"\bdays?\s+until\s+(.+?)(?:\?|$)", re.I
)
_DATE_DAYS_FROM = re.compile(
    r"\b(\d+)\s+days?\s+from\s+(?:today|now)\b", re.I
)
_DATE_WEEKS_FROM = re.compile(
    r"\b(\d+)\s+weeks?\s+from\s+(?:today|now)\b", re.I
)
_DATE_AGE = re.compile(
    r"\b(?:age\s+(?:of\s+)?(?:someone\s+)?born|born\s+on?)\s+"
    r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4})\b",
    re.I,
)

_NAMED_DATES: dict[str, str] = {
    "new year": "01-01",
    "new year's": "01-01",
    "christmas": "12-25",
    "christmas day": "12-25",
    "valentine's day": "02-14",
    "halloween": "10-31",
    "thanksgiving": "11-01",  # approximate — 4th Thursday
}


def _try_date_math(text: str) -> dict | None:
    today = date.today()

    # days until <event>
    m = _DATE_DAYS_UNTIL.search(text)
    if m:
        event_raw = m.group(1).strip().lower().rstrip("?.,")
        target = None
        for name, mmdd in _NAMED_DATES.items():
            if name in event_raw:
                year = today.year
                candidate = date.fromisoformat(f"{year}-{mmdd}")
                if candidate < today:
                    candidate = date.fromisoformat(f"{year+1}-{mmdd}")
                target = candidate
                event_label = name.title()
                break
        if target:
            delta = (target - today).days
            return {
                "kind": "date",
                "result": f"{delta} days",
                "label": f"Days until {event_label}",
                "detail": f"Today is {today.strftime('%B %d, %Y')} · {target.strftime('%B %d, %Y')}",
            }

    # N days / weeks from today
    m = _DATE_DAYS_FROM.search(text)
    if m:
        n = int(m.group(1))
        target = today + timedelta(days=n)
        return {
            "kind": "date",
            "result": target.strftime("%B %d, %Y"),
            "label": f"{n} days from today",
            "detail": f"Today is {today.strftime('%B %d, %Y')} · {target.strftime('%A')}",
        }

    m = _DATE_WEEKS_FROM.search(text)
    if m:
        n = int(m.group(1))
        target = today + timedelta(weeks=n)
        return {
            "kind": "date",
            "result": target.strftime("%B %d, %Y"),
            "label": f"{n} weeks from today",
            "detail": f"Today is {today.strftime('%B %d, %Y')} · {target.strftime('%A')}",
        }

    # age calculation
    m = _DATE_AGE.search(text)
    if m:
        raw = m.group(1).replace("/", "-")
        try:
            # Handle both YYYY-MM-DD and DD-MM-YYYY
            parts = raw.split("-")
            if len(parts[0]) == 4:
                bd = date.fromisoformat(raw)
            else:
                bd = date(int(parts[2]), int(parts[1]), int(parts[0]))
            age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
            return {
                "kind": "date",
                "result": f"{age} years old",
                "label": f"Age born {bd.strftime('%B %d, %Y')}",
                "detail": f"Born {bd.strftime('%B %d, %Y')} · {today.strftime('%B %d, %Y')}",
            }
        except (ValueError, IndexError):
            pass

    return None


# ── Timezone diff ─────────────────────────────────────────────────────────────

_TZ_DIFF = re.compile(
    r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+(?:in\s+)?(\w[\w\s]+?)\s+in\s+(\w[\w\s]+?)(?:\?|$)",
    re.I,
)


def _try_tz_diff(text: str) -> dict | None:
    m = _TZ_DIFF.search(text)
    if not m:
        return None
    h, mins, ampm, city_from, city_to = m.groups()
    h = int(h)
    mins = int(mins or 0)
    if ampm:
        if ampm.lower() == "pm" and h != 12:
            h += 12
        elif ampm.lower() == "am" and h == 12:
            h = 0

    zone_from = _find_zone(city_from)
    zone_to = _find_zone(city_to)
    if not zone_from or not zone_to:
        return None

    try:
        today = date.today()
        dt_from = datetime(today.year, today.month, today.day, h, mins,
                           tzinfo=ZoneInfo(zone_from))
        dt_to = dt_from.astimezone(ZoneInfo(zone_to))
        label_from = city_from.strip().title()
        label_to = city_to.strip().title()
        time_from = dt_from.strftime("%I:%M %p").lstrip("0")
        time_to = dt_to.strftime("%I:%M %p").lstrip("0")
        return {
            "kind": "timezone_diff",
            "result": time_to,
            "label": f"{time_from} {label_from} → {label_to}",
            "detail": f"{dt_to.strftime('%A, %B %d')}",
        }
    except (ZoneInfoNotFoundError, ValueError):
        return None


# ── Base / number conversion ──────────────────────────────────────────────────

_BASE_Q = re.compile(
    r"\b(\d+|0x[0-9a-fA-F]+|0b[01]+|0o[0-7]+)\s+"
    r"(?:in|to|as)\s+"
    r"(hex(?:adecimal)?|binary|octal|decimal)\b",
    re.I,
)


def _try_base_conv(text: str) -> dict | None:
    m = _BASE_Q.search(text)
    if not m:
        return None
    raw, target = m.group(1), m.group(2).lower()
    try:
        # Parse the number
        if raw.lower().startswith("0x"):
            n = int(raw, 16)
        elif raw.lower().startswith("0b"):
            n = int(raw, 2)
        elif raw.lower().startswith("0o"):
            n = int(raw, 8)
        else:
            n = int(raw)

        if target.startswith("hex"):
            result = hex(n)
            label = "Hexadecimal"
        elif target == "binary":
            result = bin(n)
            label = "Binary"
        elif target == "octal":
            result = oct(n)
            label = "Octal"
        else:
            result = str(n)
            label = "Decimal"

        return {
            "kind": "base_conv",
            "result": result,
            "label": f"{raw} in {label}",
            "detail": f"dec={n}  hex={hex(n)}  bin={bin(n)}",
        }
    except (ValueError, OverflowError):
        return None


# ── Hash / encode ─────────────────────────────────────────────────────────────

_HASH_Q = re.compile(
    r"\b(md5|sha1|sha256|sha512)\s+(?:of\s+)?[\"']?(.+?)[\"']?(?:\?|$)", re.I
)
_B64_ENCODE = re.compile(
    r"\bbase64\s+(?:encode\s+)?[\"']?(.+?)[\"']?(?:\?|$)", re.I
)
_B64_DECODE = re.compile(
    r"\bbase64\s+decode\s+[\"']?([A-Za-z0-9+/=]+)[\"']?(?:\?|$)", re.I
)
_URL_ENCODE = re.compile(
    r"\b(?:url[_-]?encode|percent[_-]?encode)\s+[\"']?(.+?)[\"']?(?:\?|$)", re.I
)


def _try_hash_encode(text: str) -> dict | None:
    m = _HASH_Q.search(text)
    if m:
        algo, payload = m.group(1).lower(), m.group(2).strip()
        try:
            h = hashlib.new(algo, payload.encode()).hexdigest()
            return {"kind": "hash", "result": h, "label": f"{algo.upper()} of '{payload}'"}
        except Exception:
            return None

    m = _B64_DECODE.search(text)
    if m:
        try:
            decoded = base64.b64decode(m.group(1)).decode("utf-8", errors="replace")
            return {"kind": "encode", "result": decoded, "label": "Base64 decoded"}
        except Exception:
            return None

    m = _B64_ENCODE.search(text)
    if m:
        payload = m.group(1).strip()
        result = base64.b64encode(payload.encode()).decode()
        return {"kind": "encode", "result": result, "label": f"Base64 encode of '{payload}'"}

    m = _URL_ENCODE.search(text)
    if m:
        payload = m.group(1).strip()
        result = urllib.parse.quote(payload)
        return {"kind": "encode", "result": result, "label": f"URL-encoded"}

    return None


# ── Color conversion ──────────────────────────────────────────────────────────

_HEX_COLOR = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
_RGB_COLOR = re.compile(
    r"rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)", re.I
)


def _try_color(text: str) -> dict | None:
    # Hex → RGB
    m = _HEX_COLOR.search(text)
    if m and re.search(r"\b(?:to\s+)?rgb\b", text, re.I):
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c*2 for c in h)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return {
            "kind": "color",
            "result": f"rgb({r}, {g}, {b})",
            "label": f"#{h.upper()} → RGB",
            "hex": f"#{h.upper()}",
            "rgb": [r, g, b],
        }

    # RGB → Hex
    m = _RGB_COLOR.search(text)
    if m and re.search(r"\b(?:to\s+)?hex\b", text, re.I):
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        result = f"#{r:02X}{g:02X}{b:02X}"
        return {
            "kind": "color",
            "result": result,
            "label": f"rgb({r},{g},{b}) → Hex",
            "hex": result,
            "rgb": [r, g, b],
        }

    return None


# ── Tip / split ───────────────────────────────────────────────────────────────

_TIP_SPLIT = re.compile(
    r"split\s+\$?([\d,]+(?:\.\d{2})?)\s+(\d+)\s+ways?\s+with\s+([\d.]+)\s*%\s+tip",
    re.I,
)
_TIP_ONLY = re.compile(
    r"([\d.]+)\s*%\s+tip\s+(?:on\s+)?\$?([\d,]+(?:\.\d{2})?)", re.I
)


def _try_tip_split(text: str) -> dict | None:
    m = _TIP_SPLIT.search(text)
    if m:
        try:
            total = float(m.group(1).replace(",", ""))
            ways = int(m.group(2))
            pct = float(m.group(3))
            tip = total * pct / 100
            grand = total + tip
            per = grand / ways
            return {
                "kind": "tip_split",
                "result": f"${per:.2f} each",
                "label": f"${total:.2f} bill, {pct:.0f}% tip, split {ways} ways",
                "detail": (
                    f"Tip: ${tip:.2f}  ·  Total: ${grand:.2f}  ·  Per person: ${per:.2f}"
                ),
            }
        except (ValueError, ZeroDivisionError):
            return None

    m = _TIP_ONLY.search(text)
    if m:
        try:
            pct = float(m.group(1))
            total = float(m.group(2).replace(",", ""))
            tip = total * pct / 100
            return {
                "kind": "tip_split",
                "result": f"${tip:.2f}",
                "label": f"{pct:.0f}% tip on ${total:.2f}",
                "detail": f"Total with tip: ${total + tip:.2f}",
            }
        except ValueError:
            return None

    return None


# ── Public entry point ────────────────────────────────────────────────────────

def try_local(text: str) -> dict | None:
    """Try all local deterministic tools. Return card payload or None."""
    return (
        _try_date_math(text)
        or _try_tz_diff(text)
        or _try_base_conv(text)
        or _try_hash_encode(text)
        or _try_color(text)
        or _try_tip_split(text)
    )
