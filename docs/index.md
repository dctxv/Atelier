# Atelier — Documentation

*Written by Clay. Last updated June 2026.*

---

Atelier is my personal AI workspace. The idea is simple: I want to talk to any model I already have access to — OpenRouter, Ollama, a local LM Studio instance, whatever — without going through someone else's product UI. I want the experience to feel like mine. The name comes from the French for a craftsman's workshop or artist's studio. That's the tone I was going for. Quiet, deliberate, yours.

This isn't meant to be shared software in the polished sense. It runs locally. But I do care a lot about how it looks and feels, which is why a meaningful amount of thought went into things that a utility app would never bother with — typefaces, rhythm, the way a response fades up.

These docs exist so that when I come back to this in six months, or when I hand it off to someone, the thinking is all here — not just what was built, but why it was built that way and what I decided not to do.

> The backend runs on a **shared core** — one SQLite database, one embedding function, one retrieval layer, one job system — and every feature plugs into it. Auth is opt-in: off by default on `127.0.0.1`, ready when bound to the LAN. See [shared-core.md](shared-core.md) for the architecture and [latency-testing.md](latency-testing.md) for the bench results.

---

## What's been built

### Frontend & design

| Document | What it covers |
|---|---|
| [design-system.md](design-system.md) | Visual direction, typefaces, color tokens, themes, animation |
| [frontend-architecture.md](frontend-architecture.md) | How the frontend is structured — no build step, JSX loader, local lib serving |
| [shell-navigation.md](shell-navigation.md) | Left rail, chat tab bar, drag-scroll, theme toggle |
| [chat-surface.md](chat-surface.md) | Chat UI, SSE streaming, session persistence, model selection, command palette, block rendering |
| [setup-flow.md](setup-flow.md) | Welcome modal, 4-step API endpoint wizard (incl. background model), first-run experience |
| [repository.md](repository.md) | Git setup, secret protection, start.ps1 |

### Backend — the shared core and the features on top of it

| Document | What it covers |
|---|---|
| [shared-core.md](shared-core.md) | The one database / one embed / one retrieval / one job system everything plugs into |
| [memory.md](memory.md) | Living Memory System v2 — structured atoms, predicate categories, decay, reconciliation, hypotheses, drift, all endpoints |
| [memory-prescient.md](memory-prescient.md) | Prescient Memory Part 1 — strands, stale-self-image guard, suppression atoms, warming, hypothesis engine v2, weekly diff |
| [web-search.md](web-search.md) | The search layer — freshness, cache, provider fallback chain, rerank, real-time |
| [research-pipeline.md](research-pipeline.md) | Planner → parallel sub-agents → grounded synthesis |
| [mcp.md](mcp.md) | Acting as an MCP client, the approval gate for destructive tools |
| [latency-testing.md](latency-testing.md) | The instrumentation, the bench harness, and the bottlenecks I actually found |
| [v2-deferred.md](v2-deferred.md) | What's still deferred |

---

## What this is (and isn't)

Atelier is a local tool I run for myself, on `127.0.0.1:8000`. It is not a production SaaS, it doesn't sync to the cloud, and it stays single-user by default. What changed in v1 is the *inside*: it now has a real backend that can carry weight — a shared memory, fast retrieval at scale, background work — without ever sacrificing the thing I care about, which is that nothing gets between me and a streaming reply. Keeping the surface simple while the core got serious was the whole design tension, and the [hot-path rules](shared-core.md#the-hot-path-rules) are how I held the line.
