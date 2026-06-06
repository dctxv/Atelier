"""Search layer management: providers, encrypted keys, fallback order, metrics."""
from __future__ import annotations

from fastapi import APIRouter, Request

from services import config, search
from services.search import registry, usage

router = APIRouter(prefix="/api/search")


@router.get("/providers")
async def list_providers():
    out = []
    for name, prov in registry.all_providers().items():
        out.append({
            "name": name,
            "available": await prov.available(),
            "cost_per_call": prov.cost_per_call,
            "supports_recency": prov.supports_recency,
            "has_key": await config.has_secret(f"{name}_api_key"),
            "free_cap": usage.FREE_CAPS.get(name),
            "remaining": await usage.remaining(name),
        })
    return {"providers": out, "order": await registry.order()}


@router.put("/keys")
async def set_keys(request: Request):
    data = await request.json()
    for provider in ("tavily", "brave"):
        if provider in data:
            await config.set_secret(f"{provider}_api_key", data[provider] or "")
    return {"ok": True}


@router.put("/order")
async def set_order(request: Request):
    data = await request.json()
    order = data.get("order", [])
    if isinstance(order, list):
        await config.set_setting("search_provider_order", ",".join(order))
    return {"ok": True, "order": await registry.order()}


@router.get("/metrics")
async def search_metrics():
    return await search.metrics_summary()
