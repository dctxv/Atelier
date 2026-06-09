"""Minimal MCP (Model Context Protocol) client (Part 2.8).

Atelier acts as an MCP *client* so chat can invoke MCP tools. v1 is the
simplest viable form:
  - Talk to MCP servers over stdio with newline-delimited JSON-RPC.
  - Start with read-only / non-destructive tools.
  - Destructive / side-effectful calls require explicit in-UI approval
    (the router refuses unless approved=True).
  - Every call is logged to mcp_call_log.

Servers are configured in app_config under 'mcp_servers' as JSON:
  [{"name":"files","command":"npx","args":["-y","@modelcontextprotocol/server-filesystem","/safe/dir"]}]

No persistent connections in v1: each operation runs a short stdio session.
That trades a little startup latency for simplicity and isolation — and tool
calls are explicitly off the default reply path, so latency is not critical.
"""
from __future__ import annotations

import asyncio
import json
import uuid

from . import config, db

PROTOCOL_VERSION = "2024-11-05"


async def _servers() -> list[dict]:
    raw = await config.get_setting("mcp_servers")
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []


async def _server(name: str) -> dict | None:
    for s in await _servers():
        if s.get("name") == name:
            return s
    return None


class _Stdio:
    """One short JSON-RPC-over-stdio session against an MCP server process."""

    def __init__(self, command: str, args: list[str]):
        self.command = command
        self.args = args
        self.proc: asyncio.subprocess.Process | None = None
        self._id = 0

    async def __aenter__(self):
        self.proc = await asyncio.create_subprocess_exec(
            self.command, *self.args,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "the-atelier", "version": "1.0"},
        })
        await self._notify("notifications/initialized", {})
        return self

    async def __aexit__(self, *exc):
        if self.proc:
            try:
                self.proc.terminate()
                await asyncio.wait_for(self.proc.wait(), timeout=3)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass

    async def _send(self, message: dict):
        assert self.proc and self.proc.stdin
        self.proc.stdin.write((json.dumps(message) + "\n").encode())
        await self.proc.stdin.drain()

    async def _notify(self, method: str, params: dict):
        await self._send({"jsonrpc": "2.0", "method": method, "params": params})

    async def _request(self, method: str, params: dict) -> dict:
        self._id += 1
        req_id = self._id
        await self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        assert self.proc and self.proc.stdout
        while True:
            line = await asyncio.wait_for(self.proc.stdout.readline(), timeout=30)
            if not line:
                raise RuntimeError("MCP server closed the connection")
            try:
                msg = json.loads(line.decode())
            except Exception:
                continue
            if msg.get("id") == req_id:
                if "error" in msg:
                    raise RuntimeError(msg["error"].get("message", "MCP error"))
                return msg.get("result", {})

    async def list_tools(self) -> list[dict]:
        return (await self._request("tools/list", {})).get("tools", [])

    async def call_tool(self, name: str, arguments: dict) -> dict:
        return await self._request("tools/call", {"name": name, "arguments": arguments})


def _is_destructive(tool: dict) -> bool:
    """A tool is treated as needing approval unless it declares read-only."""
    ann = tool.get("annotations") or {}
    if ann.get("readOnlyHint") is True:
        return False
    if ann.get("destructiveHint") is True:
        return True
    # Default-safe: unknown side effects require approval.
    return True


async def list_all_tools() -> dict:
    out = {}
    for s in await _servers():
        try:
            async with _Stdio(s["command"], s.get("args", [])) as session:
                tools = await session.list_tools()
                out[s["name"]] = [{**t, "requires_approval": _is_destructive(t)} for t in tools]
        except Exception as e:  # noqa: BLE001
            out[s["name"]] = {"error": str(e)}
    return out


async def _log(server: str, tool: str, args: dict, result, approved: bool, error: str | None):
    await db.execute(
        "INSERT INTO mcp_call_log(id, server, tool, args, result, approved, error, created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), server, tool, json.dumps(args),
         json.dumps(result)[:8000] if result is not None else None,
         int(approved), error, db.now()),
    )


async def call(server_name: str, tool_name: str, arguments: dict, approved: bool = False) -> dict:
    """Invoke a tool. Returns {needs_approval:True} if destructive and not approved."""
    server = await _server(server_name)
    if not server:
        raise ValueError(f"unknown MCP server '{server_name}'")

    async with _Stdio(server["command"], server.get("args", [])) as session:
        tools = await session.list_tools()
        spec = next((t for t in tools if t.get("name") == tool_name), None)
        if not spec:
            raise ValueError(f"unknown tool '{tool_name}'")

        if _is_destructive(spec) and not approved:
            return {"needs_approval": True, "tool": tool_name,
                    "description": spec.get("description", "")}

        try:
            result = await session.call_tool(tool_name, arguments)
            await _log(server_name, tool_name, arguments, result, approved, None)
            return {"ok": True, "result": result}
        except Exception as e:  # noqa: BLE001
            await _log(server_name, tool_name, arguments, None, approved, str(e))
            raise


async def recent_log(limit: int = 50) -> list[dict]:
    return await db.fetchall(
        "SELECT id, server, tool, args, approved, error, created_at FROM mcp_call_log "
        "ORDER BY created_at DESC LIMIT ?", (limit,)
    )
