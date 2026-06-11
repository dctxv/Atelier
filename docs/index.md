# Atelier — Documentation

*Written by Clay. Last updated June 2026.*

---

Atelier is my personal AI workspace. The idea is simple: I want to talk to any model I already have access to — OpenRouter, Ollama, a local LM Studio instance, whatever — without going through someone else's product UI. I want the experience to feel like mine. The name comes from the French for a craftsman's workshop or artist's studio. That's the tone I was going for. Quiet, deliberate, yours.

This isn't meant to be shared software in the polished sense. It runs locally. But I do care a lot about how it looks and feels, which is why a meaningful amount of thought went into things that a utility app would never bother with — typefaces, rhythm, the way a response fades up.

These docs exist so that when I come back to this in six months, or when I hand it off to someone, the thinking is all here — not just what was built, but why it was built that way and what I decided not to do.

> **A note on the evolution.** Earlier versions of these docs said "there's no database because I don't need one yet" and "there's no auth because I'm the only user." Both were true for the first iteration — the whole app ran on a handful of `data/*.json` files. That stopped scaling the moment I wanted the surfaces to actually *talk to each other*: a shared memory that chat writes to and research reads from, retrieval that works at fifty thousand entries, background jobs that don't block a reply. So I rebuilt the backend around a **shared core** — one SQLite database, one embedding function, one retrieval layer, one job system — and every feature now plugs into it. Auth exists too, but it's deliberately opt-in: still off by default on `127.0.0.1`, ready the day I bind to the LAN. The JSON era is documented where relevant because the migration path matters, but the JSON files are retired. See [shared-core.md](shared-core.md) for the architecture and [latency-testing.md](latency-testing.md) for how I proved it's fast.

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
| [surfaces.md](surfaces.md) | Memory, Notes, and Research surfaces (frontend) |
| [inline-rendering.md](inline-rendering.md) | Bold text, emoji fix, inline markdown parsing |
| [repository.md](repository.md) | Git setup, secret protection, start.ps1 |

### Backend — the shared core and the features on top of it

| Document | What it covers |
|---|---|
| [shared-core.md](shared-core.md) | The one database / one embed / one retrieval / one job system everything plugs into |
| [memory.md](memory.md) | Living Memory System v2 — structured atoms, predicate categories, decay, reconciliation, hypotheses, drift, all endpoints |
| [memory-tier-selection.md](memory-tier-selection.md) | Tier selection setup screen, opt-in gating, Basic / Reflective / Prescient depth system |
| [flashcards.md](flashcards.md) | FSRS-6 scheduling, decks, paste import, AI card generation |
| [sharing.md](sharing.md) | Expiring share links over uploaded files |
| [web-search.md](web-search.md) | The search layer — freshness, cache, provider fallback chain, rerank, real-time |
| [research-pipeline.md](research-pipeline.md) | Planner → parallel sub-agents → grounded synthesis → memory |
| [notes-cowriter.md](notes-cowriter.md) | Selection-based AI writing actions, ingest-on-save |
| [email.md](email.md) | IMAP sync, categorize, on-demand drafts, explicit-send-only |
| [mcp.md](mcp.md) | Acting as an MCP client, the approval gate for destructive tools |
| [latency-testing.md](latency-testing.md) | The instrumentation, the bench harness, and the bottlenecks I actually found |
| [v2-deferred.md](v2-deferred.md) | What's still deferred (and what shipped in v2) |

---

## What this is (and isn't)

Atelier is a local tool I run for myself, on `127.0.0.1:8000`. It is not a production SaaS, it doesn't sync to the cloud, and it stays single-user by default. What changed in v1 is the *inside*: it now has a real backend that can carry weight — a shared memory, fast retrieval at scale, background work — without ever sacrificing the thing I care about, which is that nothing gets between me and a streaming reply. Keeping the surface simple while the core got serious was the whole design tension, and the [hot-path rules](shared-core.md#the-hot-path-rules) are how I held the line.
