"""LLM helpers over the shared httpx client.

Two tiers, per hot-path rule 3:
  - complete(): big-model, non-streaming, for synthesis / drafts.
  - cheap(): the configured cheap/local model for extraction, classification,
    card generation. Falls back to the active model if no cheap model is set.

Streaming for user-facing chat lives in routers/chat.py (it needs the raw SSE
proxy); these helpers are for background and one-shot calls.

Task-tier routing (Extension B):
  cheap() accepts an optional `task` name. The task_tiers config maps task names
  to "cheap" or "active". If no tier is configured for a task, defaults to cheap.

Usage telemetry (Extension C):
  Every call records token counts and estimated cost to usage_daily. Provider
  responses that omit usage are handled gracefully (recorded as 0).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from . import config, db, http_client

# Default task → tier mapping. Can be overridden via app_config key "task_tiers"
# (stored as JSON). "cheap" uses cheap_model; "active" uses active_model.
_DEFAULT_TASK_TIERS: dict[str, str] = {
    "chat_reply":            "active",
    "memory_extraction":     "cheap",
    "categorization":        "cheap",
    "research_plan":         "cheap",
    "research_gap":          "cheap",
    "claim_verify":          "cheap",
    "research_synthesis":    "active",
    "document_abstract":     "cheap",
    "card_generation":       "cheap",
    "cowriter":              "active",
    # Prescient memory (P1.0–P1.6)
    "strand_cluster":        "cheap",
    "hypothesis_generation": "cheap",
    "hypothesis_nli":        "cheap",
    "weekly_diff_summary":   "cheap",
}


async def _task_tiers() -> dict[str, str]:
    raw = await config.get_setting("task_tiers")
    if not raw:
        return _DEFAULT_TASK_TIERS
    try:
        overrides = json.loads(raw)
        return {**_DEFAULT_TASK_TIERS, **overrides}
    except Exception:
        return _DEFAULT_TASK_TIERS


async def _record_usage(model: str, task: str, response_json: dict) -> None:
    """Write token usage to usage_daily. Best-effort — never raises."""
    try:
        usage = response_json.get("usage") or {}
        input_tok = int(usage.get("prompt_tokens", 0))
        output_tok = int(usage.get("completion_tokens", 0))

        # Estimate cost from model registry if present; else 0.
        reg = await db.fetchone("SELECT input_price, output_price FROM model_registry WHERE id=?", (model,))
        est = 0.0
        if reg:
            ip = reg.get("input_price") or 0.0
            op = reg.get("output_price") or 0.0
            est = (input_tok * ip + output_tok * op) / 1_000_000

        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        await db.execute(
            "INSERT INTO usage_daily(day, model, task, input_tokens, output_tokens, est_cost_usd) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(day,model,task) DO UPDATE SET "
            "input_tokens=input_tokens+excluded.input_tokens, "
            "output_tokens=output_tokens+excluded.output_tokens, "
            "est_cost_usd=est_cost_usd+excluded.est_cost_usd",
            (day, model, task, input_tok, output_tok, est),
        )
    except Exception:
        pass  # telemetry must never break a real call


async def _post_chat(
    ep: dict,
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int | None,
    task: str = "unknown",
) -> str:
    payload = {"model": model, "messages": messages, "stream": False, "temperature": temperature}
    if max_tokens:
        payload["max_tokens"] = max_tokens
    resp = await http_client.client().post(
        f"{ep['url']}/chat/completions", json=payload, headers=config.headers(ep), timeout=240
    )
    resp.raise_for_status()
    data = resp.json()
    await _record_usage(model, task, data)
    return data["choices"][0]["message"]["content"].strip()


async def complete(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int | None = None,
    model: str | None = None,
    task: str = "chat_reply",
) -> str:
    ep = await config.active_endpoint_raw()
    if not ep:
        raise RuntimeError("No active endpoint configured")
    model = model or await config.get_setting("active_model")
    if not model:
        raise RuntimeError("No active model selected")
    return await _post_chat(ep, model, messages, temperature, max_tokens, task)


async def cheap(
    messages: list[dict],
    temperature: float = 0.2,
    max_tokens: int | None = 512,
    task: str = "unknown",
) -> str:
    """Use the cheap model when configured; otherwise the active model."""
    ep = await config.active_endpoint_raw()
    if not ep:
        raise RuntimeError("No active endpoint configured")
    model = await config.get_setting("cheap_model") or await config.get_setting("active_model")
    if not model:
        raise RuntimeError("No model available for cheap calls")
    return await _post_chat(ep, model, messages, temperature, max_tokens, task)


async def route(
    task: str,
    messages: list[dict],
    temperature: float = 0.2,
    max_tokens: int | None = 512,
) -> str:
    """Route a call to the right model tier based on the task name."""
    tiers = await _task_tiers()
    tier = tiers.get(task, "cheap")
    if tier == "active":
        return await complete(messages, temperature=temperature, max_tokens=max_tokens, task=task)
    return await cheap(messages, temperature=temperature, max_tokens=max_tokens, task=task)
