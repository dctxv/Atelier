"""Config, endpoints, models, probe."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from services import config, http_client

router = APIRouter(prefix="/api")


@router.get("/config")
async def get_config():
    return await config.public_config()


@router.patch("/config")
async def patch_config(request: Request):
    data = await request.json()
    for key in ("active_endpoint_id", "active_model", "cheap_model",
                "embedding_endpoint_id", "embedding_model", "system_prompt"):
        if key in data:
            await config.set_setting(key, data[key])
    return {"ok": True}


@router.get("/endpoints")
async def list_endpoints():
    return {"endpoints": await config.list_endpoints()}


@router.post("/endpoints")
async def add_endpoint(request: Request):
    data = await request.json()
    if not data.get("url"):
        raise HTTPException(400, "url required")
    ep = await config.add_endpoint(
        name=data.get("name", "Unnamed"), url=data["url"],
        api_key=data.get("api_key", ""), type_=data.get("type", "local"),
    )
    return {"endpoint": ep}


@router.delete("/endpoints/{endpoint_id}")
async def delete_endpoint(endpoint_id: str):
    await config.delete_endpoint(endpoint_id)
    return {"ok": True}


@router.post("/endpoints/{endpoint_id}/activate")
async def activate_endpoint(endpoint_id: str):
    if not await config.activate_endpoint(endpoint_id):
        raise HTTPException(404, "Endpoint not found")
    return {"ok": True}


@router.get("/models")
async def get_models():
    ep = await config.active_endpoint_raw()
    if not ep:
        return {"models": [], "error": "No active endpoint configured"}
    try:
        resp = await http_client.client().get(f"{ep['url']}/models", headers=config.headers(ep), timeout=10)
        resp.raise_for_status()
        return {"models": [m["id"] for m in resp.json().get("data", [])]}
    except Exception as e:  # noqa: BLE001
        return {"models": [], "error": str(e)}


@router.post("/models/probe")
async def probe_endpoint(request: Request):
    data = await request.json()
    url = config._normalize(data["url"])
    headers = {"Content-Type": "application/json"}
    if data.get("api_key"):
        headers["Authorization"] = f"Bearer {data['api_key']}"
    try:
        resp = await http_client.client().get(f"{url}/models", headers=headers, timeout=10)
        resp.raise_for_status()
        return {"ok": True, "models": [m["id"] for m in resp.json().get("data", [])], "url": url}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "models": []}

@router.put("/weather/keys")
async def set_weather_keys(request: Request):
    data = await request.json()
    if "openweathermap" in data:
        await config.set_secret("weather_api_key", data["openweathermap"])
    return {"ok": True}

@router.put("/stock/keys")
async def set_stock_keys(request: Request):
    data = await request.json()
    if "finnhub" in data:
        await config.set_secret("stock_api_key", data["finnhub"])
    return {"ok": True}
