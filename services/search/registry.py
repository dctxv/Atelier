"""Provider registry + active fallback order (Part 5 A3 / B3).

Instantiates every provider once and exposes the ordered fallback chain. The
order is config (app_config 'search_provider_order'), so changing the chain — or
adding a provider — is configuration, not code surgery.
"""
from __future__ import annotations

from .. import config
from .base import SearchProvider
from .providers.brave import BraveProvider
from .providers.duckduckgo import DuckDuckGoProvider
from .providers.searxng import SearxngProvider
from .providers.tavily import TavilyProvider

_PROVIDERS: dict[str, SearchProvider] = {
    p.name: p for p in (TavilyProvider(), BraveProvider(), SearxngProvider(), DuckDuckGoProvider())
}

DEFAULT_ORDER = ["tavily", "brave", "searxng", "duckduckgo"]


def get(name: str) -> SearchProvider | None:
    return _PROVIDERS.get(name)


def all_providers() -> dict[str, SearchProvider]:
    return dict(_PROVIDERS)


async def order() -> list[str]:
    raw = await config.get_setting("search_provider_order")
    if raw:
        names = [n.strip() for n in raw.split(",") if n.strip() in _PROVIDERS]
        if names:
            return names
    return DEFAULT_ORDER


async def available_chain() -> list[SearchProvider]:
    """The fallback chain, in order, filtered to currently-available providers."""
    chain = []
    for name in await order():
        prov = _PROVIDERS.get(name)
        if prov and await prov.available():
            chain.append(prov)
    return chain
