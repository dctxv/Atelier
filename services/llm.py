"""LLM helpers over the shared httpx client.

Two tiers, per hot-path rule 3:
  - complete(): big-model, non-streaming, for synthesis / drafts.
  - cheap(): the configured cheap/local model for extraction, classification,
    card generation. Falls back to the active model if no cheap model is set.

Streaming for user-facing chat lives in routers/chat.py (it needs the raw SSE
proxy); these helpers are for background and one-shot calls.
"""
from __future__ import annotations

from . import config, http_client


async def _post_chat(ep: dict, model: str, messages: list[dict], temperature: float, max_tokens: int | None):
    payload = {"model": model, "messages": messages, "stream": False, "temperature": temperature}
    if max_tokens:
        payload["max_tokens"] = max_tokens
    resp = await http_client.client().post(
        f"{ep['url']}/chat/completions", json=payload, headers=config.headers(ep), timeout=240
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


async def complete(messages: list[dict], temperature: float = 0.3, max_tokens: int | None = None,
                   model: str | None = None) -> str:
    ep = await config.active_endpoint_raw()
    if not ep:
        raise RuntimeError("No active endpoint configured")
    model = model or await config.get_setting("active_model")
    if not model:
        raise RuntimeError("No active model selected")
    return await _post_chat(ep, model, messages, temperature, max_tokens)


async def cheap(messages: list[dict], temperature: float = 0.2, max_tokens: int | None = 512) -> str:
    """Use the cheap model when configured; otherwise the active model."""
    ep = await config.active_endpoint_raw()
    if not ep:
        raise RuntimeError("No active endpoint configured")
    model = await config.get_setting("cheap_model") or await config.get_setting("active_model")
    if not model:
        raise RuntimeError("No model available for cheap calls")
    return await _post_chat(ep, model, messages, temperature, max_tokens)
