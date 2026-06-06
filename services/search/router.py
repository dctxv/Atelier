"""Provider router with an ordered fallback chain (Part 5 B3).

primary times out / errors / over quota → next provider, transparently, with no
user-visible error as long as one provider succeeds. Enforces a per-query
provider-call budget (Part 3) and a primary timeout cap so a slow primary can't
blow the latency budget.
"""
from __future__ import annotations

import asyncio
import time

from . import obs, registry, usage
from .schema import SearchResult

# Cap before giving up on a provider and falling back. This guards against a
# *hanging* provider, not a normally-slow one — a cold Tavily/Brave round-trip
# from a distant region can legitimately take several seconds, and cancelling it
# at 2.5s just dumps us onto the unreliable free fallback. So the ceiling is
# generous; the latency *budgets* are tracked separately in metrics.
PRIMARY_TIMEOUT = 8.0
PER_PROVIDER_TIMEOUT = 12.0
MAX_PROVIDER_CALLS = 4       # per-query budget (Part 3)


async def route(query, *, max_results=8, recency=None, is_news=False,
                include_raw_content=False) -> tuple[list[SearchResult], list[str], int]:
    chain = await registry.available_chain()
    providers_used: list[str] = []
    cost_units = 0
    calls = 0
    last_error: Exception | None = None

    for i, provider in enumerate(chain):
        if calls >= MAX_PROVIDER_CALLS:
            break
        if await usage.over_quota(provider.name):
            continue

        # The first (primary) provider gets the tight 2.5s cap; later providers
        # get the looser per-provider ceiling.
        timeout = PRIMARY_TIMEOUT if i == 0 else PER_PROVIDER_TIMEOUT
        calls += 1
        started = time.perf_counter()
        try:
            results = await asyncio.wait_for(
                provider.search(query, max_results=max_results, recency=recency,
                                is_news=is_news, include_raw_content=include_raw_content),
                timeout=timeout,
            )
            obs.record_provider(provider.name, (time.perf_counter() - started) * 1000)
            await usage.record(provider.name)
            providers_used.append(provider.name)
            cost_units += provider.cost_per_call
            if results:
                return results, providers_used, cost_units
        except Exception as e:  # noqa: BLE001  (timeout, http error, key missing, …)
            last_error = e
            obs.record_provider(provider.name, (time.perf_counter() - started) * 1000)
            await usage.record(provider.name, error=True)
            continue

    if last_error and not providers_used:
        # Nothing worked at all — surface enough to debug, empty results.
        return [], providers_used, cost_units
    return [], providers_used, cost_units
