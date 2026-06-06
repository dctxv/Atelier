"""The single shared httpx.AsyncClient (Part 1.5 / hot-path rule 5).

Created once in the app lifespan and reused everywhere — chat streaming,
embeddings, model probing, research fetches. Creating a client per request is
a real latency tax (new TLS handshake, no connection reuse), so we never do it.
"""
from __future__ import annotations

import httpx

_client: httpx.AsyncClient | None = None


def set_client(c: httpx.AsyncClient) -> None:
    global _client
    _client = c


def client() -> httpx.AsyncClient:
    if _client is None:
        raise RuntimeError("Shared httpx client not initialised (lifespan not run)")
    return _client
