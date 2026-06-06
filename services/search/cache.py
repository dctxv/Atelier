"""Read-through search cache (Part 5 C) — the biggest cost + latency lever.

Key = normalized query + a params hash (recency, provider order, depth, news).
A valid (TTL) hit returns immediately and increments `hits`, spending ZERO
provider calls. Writes go through the single-writer executor (no lock errors).
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid

from .. import db
from .schema import SearchResponse


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", (query or "").strip().lower())


def params_hash(query: str, params: dict) -> str:
    payload = json.dumps({"q": normalize_query(query), **params}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


async def get(key: str) -> SearchResponse | None:
    row = await db.fetchone("SELECT * FROM search_cache WHERE params_hash=?", (key,))
    if not row:
        return None
    if db.now() - row["fetched_at"] > row["ttl_seconds"]:
        return None  # expired; caller will refresh (we leave the row for overwrite)
    await db.execute("UPDATE search_cache SET hits=hits+1 WHERE params_hash=?", (key,))
    resp = SearchResponse.from_dict(json.loads(row["response_json"]))
    resp.from_cache = True
    return resp


async def put(key: str, query_norm: str, response: SearchResponse, ttl_seconds: int):
    response.from_cache = False
    body = json.dumps(response.to_dict())
    await db.execute(
        "INSERT INTO search_cache(id, query_norm, params_hash, response_json, fetched_at, ttl_seconds, hits) "
        "VALUES(?,?,?,?,?,?,0) "
        "ON CONFLICT(params_hash) DO UPDATE SET response_json=excluded.response_json, "
        "fetched_at=excluded.fetched_at, ttl_seconds=excluded.ttl_seconds, hits=0",
        (str(uuid.uuid4()), query_norm, key, body, db.now(), ttl_seconds),
    )


async def stats() -> dict:
    row = await db.fetchone(
        "SELECT COUNT(*) AS entries, COALESCE(SUM(hits),0) AS total_hits FROM search_cache"
    )
    return {"entries": row["entries"], "total_hits": row["total_hits"]}
