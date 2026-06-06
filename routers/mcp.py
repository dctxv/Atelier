"""MCP endpoints (Part 2.8): configure servers, list tools, invoke, view log."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request

from services import config, mcp

router = APIRouter(prefix="/api/mcp")


@router.get("/servers")
async def list_servers():
    raw = await config.get_setting("mcp_servers")
    return {"servers": json.loads(raw) if raw else []}


@router.put("/servers")
async def set_servers(request: Request):
    data = await request.json()
    servers = data.get("servers", [])
    await config.set_setting("mcp_servers", json.dumps(servers))
    return {"ok": True, "servers": servers}


@router.get("/tools")
async def list_tools():
    return {"tools": await mcp.list_all_tools()}


@router.post("/call")
async def call_tool(request: Request):
    data = await request.json()
    server = data.get("server")
    tool = data.get("tool")
    if not server or not tool:
        raise HTTPException(400, "server and tool required")
    try:
        result = await mcp.call(server, tool, data.get("arguments", {}), bool(data.get("approved", False)))
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, str(e))
    if result.get("needs_approval"):
        # 409: the action is blocked pending explicit approval.
        raise HTTPException(409, detail={"needs_approval": True, **result})
    return result


@router.get("/log")
async def call_log():
    return {"log": await mcp.recent_log()}
