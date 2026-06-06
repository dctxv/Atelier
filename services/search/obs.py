"""Search observability (Part 5 F3): per-provider latency, cache-hit rate,
freshness coverage, cost units — fed into /api/metrics.

In-memory rolling buffers, same rationale as the core metrics module (no
per-request DB writes on the hot path)."""
from __future__ import annotations

from collections import defaultdict, deque

_MAX = 2000
_provider_latency: dict[str, deque] = defaultdict(lambda: deque(maxlen=_MAX))
_counters = defaultdict(int)


def record_provider(provider: str, ms: float):
    _provider_latency[provider].append(ms)


def record_query(*, from_cache: bool, cost_units: int, fresh: bool, fresh_covered: bool):
    _counters["queries"] += 1
    _counters["cache_hits" if from_cache else "cache_misses"] += 1
    _counters["cost_units"] += cost_units
    if fresh:
        _counters["fresh_queries"] += 1
        if fresh_covered:
            _counters["fresh_covered"] += 1


def _pct(vals, q):
    if not vals:
        return None
    s = sorted(vals)
    return round(s[min(len(s) - 1, int(round(q / 100 * (len(s) - 1))))], 1)


def summary() -> dict:
    q = _counters["queries"] or 1
    fresh_q = _counters["fresh_queries"] or 1
    return {
        "queries": _counters["queries"],
        "cache_hit_rate": round(_counters["cache_hits"] / q, 3),
        "cost_units": _counters["cost_units"],
        "freshness_coverage": round(_counters["fresh_covered"] / fresh_q, 3),
        "provider_latency_ms": {
            p: {"p50": _pct(list(b), 50), "p95": _pct(list(b), 95), "count": len(b)}
            for p, b in _provider_latency.items() if b
        },
    }
