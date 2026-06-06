# Agents / MCP

*Acting as an MCP client, in the simplest viable form. Written by Clay.*

---

## What it does

The Atelier can be an **MCP client**: it connects to configured MCP servers, lists their tools, and lets chat invoke them. v1 is intentionally the smallest thing that works:

- Talk to MCP servers over **stdio** with newline-delimited JSON-RPC.
- Start with read-only / non-destructive tools.
- **Destructive or side-effectful calls require explicit in-UI approval** — the call endpoint refuses unless `approved=true`.
- Every call is logged to `mcp_call_log`.

Servers are configured in `app_config` under `mcp_servers`:
```json
[{"name":"files","command":"npx","args":["-y","@modelcontextprotocol/server-filesystem","/safe/dir"]}]
```

## How a call works

`services/mcp.py` runs a short stdio session per operation: spawn the server process, `initialize`, send `notifications/initialized`, then `tools/list` or `tools/call`, read the matching response, terminate. No persistent connections in v1 — that trades a little startup latency for simplicity and isolation, and tool calls are explicitly off the default reply path so latency isn't critical here.

The **approval gate** reads each tool's MCP annotations. A tool is allowed without approval only if it declares `readOnlyHint: true`. Anything that declares `destructiveHint`, or that declares nothing at all, is treated as needing approval (default-safe). If a destructive tool is called without `approved=true`, the endpoint returns **409** with `{needs_approval: true}` and the description, so the UI can prompt me before anything happens. Approved or read-only calls run and get logged with their result; failures get logged with the error.

Any local execution is meant to be sandboxed — a restricted directory, an allowlist, a timeout — which is exactly why the recommended filesystem server is pointed at a single safe directory.

---

## What I didn't build (v1)

- **Automatic tool selection by the model** mid-conversation (true agentic tool-use loops). v1 invokes a named tool explicitly; wiring the model to *decide* which tool to call, then feeding results back into the stream, is the obvious next step but it's not v1.
- **MCP over HTTP/SSE transports.** stdio only for now.
- **Persistent server connections / connection pooling.** Each call is a fresh session.
- **Resource and prompt primitives.** v1 uses the tools primitive only.
