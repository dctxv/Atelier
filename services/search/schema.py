"""The search layer's output contract (Part 1).

Consumers (chat grounding, quick lookups, the research pipeline) read these
shapes and nothing else. Providers normalize their raw output INTO SearchResult
so swapping a provider never changes what consumers see.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    content: str | None = None        # extracted clean text (top-K only)
    published_at: int | None = None   # epoch seconds, for freshness / "as of"
    score: float = 0.0                # post-rerank relevance
    source_provider: str = ""
    stale: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SearchResponse:
    query: str
    results: list[SearchResult] = field(default_factory=list)
    as_of: int | None = None
    providers_used: list[str] = field(default_factory=list)
    cost_units: int = 0
    from_cache: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @staticmethod
    def from_dict(d: dict) -> "SearchResponse":
        results = [SearchResult(**r) for r in d.get("results", [])]
        return SearchResponse(
            query=d.get("query", ""),
            results=results,
            as_of=d.get("as_of"),
            providers_used=d.get("providers_used", []),
            cost_units=d.get("cost_units", 0),
            from_cache=d.get("from_cache", False),
        )
