"""Local-first embeddings with a content-hash cache (Part 1.2).

Hot-path rules 2 & 3: embeddings are cached by content hash (never re-embed
identical text) and never depend on a paid API on the hot path.

Backends, in order of preference:
  1. An OpenAI-compatible /embeddings endpoint, when one is configured in
     app_config (embedding_endpoint_id + embedding_model). This is the
     spec-sanctioned "local LLM server embeddings endpoint" path
     (Ollama / llama.cpp / LM Studio) — no extra infra.
  2. A deterministic local hashing embedding (the "feature hashing" trick).
     It captures lexical overlap, runs in microseconds, needs no model
     download, and works fully offline — which makes it the right default and
     the right tool for the Part 4 scaling benchmark.

Whatever the backend, output is projected to db.EMBED_DIM (Matryoshka-style
truncate + renormalize) and L2-normalized, so the vec0 tables stay fixed-width
and cosine distance behaves.

EmbeddingGemma-300M via onnxruntime (the spec's first option) is deferred: it
adds a model download + runtime and the endpoint path already satisfies the
"real local embeddings" requirement. The backend is swappable behind embed().
"""
from __future__ import annotations

import hashlib
import re

import numpy as np

from . import config, db, http_client

DIM = db.EMBED_DIM


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _content_hash(text: str, model: str) -> str:
    return hashlib.sha256(f"{model}\x00{_normalize_text(text)}".encode()).hexdigest()


def _project(vec: np.ndarray) -> np.ndarray:
    """Truncate/pad to DIM and L2-normalize."""
    if vec.shape[0] >= DIM:
        out = vec[:DIM]
    else:
        out = np.zeros(DIM, dtype=np.float32)
        out[: vec.shape[0]] = vec
    norm = np.linalg.norm(out)
    if norm > 0:
        out = out / norm
    return out.astype(np.float32)


def _local_embed(text: str) -> np.ndarray:
    """Deterministic hashing embedding. Shared tokens -> higher cosine."""
    vec = np.zeros(DIM, dtype=np.float32)
    tokens = re.findall(r"[a-z0-9]+", _normalize_text(text))
    for tok in tokens:
        h = hashlib.md5(tok.encode()).digest()
        idx = int.from_bytes(h[:4], "little") % DIM
        sign = 1.0 if h[4] & 1 else -1.0
        vec[idx] += sign
    return _project(vec)


async def _endpoint_embed(text: str, ep: dict, model: str) -> np.ndarray | None:
    try:
        resp = await http_client.client().post(
            f"{ep['url']}/embeddings",
            json={"model": model, "input": text},
            headers=config.headers(ep),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()["data"][0]["embedding"]
        return _project(np.asarray(data, dtype=np.float32))
    except Exception:
        return None


async def _resolve_backend() -> tuple[dict | None, str]:
    """Return (endpoint_raw_or_None, model_name) for the active embed backend."""
    model = await config.get_setting("embedding_model")
    if not model:
        return None, "local-hash-v1"
    ep_id = await config.get_setting("embedding_endpoint_id")
    ep = await config.endpoint_raw(ep_id) if ep_id else await config.active_endpoint_raw()
    if not ep:
        return None, "local-hash-v1"
    return ep, model


async def embed(text: str) -> list[float]:
    """Embed one string. Cached by (model, normalized text)."""
    ep, model = await _resolve_backend()
    h = _content_hash(text, model)

    cached = await db.fetchone("SELECT embedding FROM embedding_cache WHERE content_hash=?", (h,))
    if cached:
        return np.frombuffer(cached["embedding"], dtype=np.float32).tolist()

    vec: np.ndarray | None = None
    if ep is not None:
        vec = await _endpoint_embed(text, ep, model)
    if vec is None:
        vec = _local_embed(text)
        model = "local-hash-v1"
        h = _content_hash(text, model)  # re-hash so the cache key matches backend

    await db.execute(
        "INSERT OR REPLACE INTO embedding_cache(content_hash, embedding, model, created_at) "
        "VALUES(?,?,?,?)",
        (h, vec.tobytes(), model, db.now()),
    )
    return vec.tolist()


async def embed_many(texts: list[str]) -> list[list[float]]:
    return [await embed(t) for t in texts]
