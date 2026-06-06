"""The uniform SearchProvider interface (Part 2).

Every provider — Tavily, Brave, SearXNG, DuckDuckGo — implements this. Adding or
swapping a provider is then config, not code surgery. A provider only has to do
one thing: turn a query into a list of normalized SearchResult.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .schema import SearchResult


class SearchProvider(ABC):
    name: str = "base"
    #: rough cost per call in "cost units" (0 for free providers)
    cost_per_call: int = 0
    #: whether this provider can return real-time / news results well
    supports_recency: bool = False

    @abstractmethod
    async def search(
        self,
        query: str,
        *,
        max_results: int = 8,
        recency: str | None = None,       # None | "day" | "week" | "month"
        is_news: bool = False,
        include_raw_content: bool = False,
    ) -> list[SearchResult]:
        ...

    async def available(self) -> bool:
        """Cheap readiness check (e.g. key present). Default: always available."""
        return True
