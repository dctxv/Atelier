# Atelier
My personal AI workspace. The idea is simple: I want to talk to any model I already have access to — OpenRouter, Ollama, LM Studio, a local llama.cpp instance, whatever — without going through someone else's product UI. The experience should feel like mine.

The name comes from the French for a craftsman's workshop or artist's studio. That's the tone I was going for. Quiet, deliberate, yours.

This runs locally on `127.0.0.1:8000`. It's not a SaaS, it doesn't sync to a cloud, and it's single-user by default. Everything persists in a single SQLite file at `data/atelier.db`.

---

## Running it

**Install dependencies:**
```bash
pip install -r requirements.txt
```

**Start the server:**
```bash
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000` in your browser. On first load, type `/setup` in the chat to connect an endpoint and configure your models.

There's no build step. No npm. No bundler. The frontend loads React 18 and Babel from `/lib/` (local files), then fetches each JSX file in a fixed order and Babel-transforms them in the browser. I chose this because it eliminates an entire class of tooling problems — no Node version conflicts, no package lock drift, no bundler config to fight. The tradeoff is that a large codebase would be slow to start; at this scale it's instant.

---

## What's built

### Chat

The core of everything. Streaming replies over SSE from any OpenAI-compatible endpoint. Sessions are stored in localStorage — the backend is stateless with respect to conversations. I chose localStorage because it's instant (no round-trip to load history), it's genuinely personal state, and clearing it is a clean reset. If I ever run this on multiple machines, I'll move sessions to the backend.

**Model selection** lives in the composer toolbar, not the header. That's where it's relevant — you're about to send, you want to confirm which model will respond.

**Command palette** — type `/` in the composer to see available actions (new session, switch model, toggle web search, open setup). Actions are discoverable; adding a new one is one object in an array.

**Message rendering** is hand-written, not a markdown library. It understands exactly the block types I need: fenced code, headings, tables, lists, inline bold and code, KaTeX math (`\( \)` and `\[ \]`). The first paragraph of a response gets promoted to a Cormorant Garamond italic lede — like a pull quote — giving responses an authored rather than mechanical quality. Code blocks are captured verbatim before any other processing, so markdown inside code is never misfired as markup.

**Provenance chips** appear under each response: `∑ computed`, `🌐 3 sources`, `🧠 memory`, `📄 file.pdf`. If a response drew on a note or research report, that chip is clickable and takes you straight to it. One glance tells you whether you're reading a web-sourced fact, a memory, or the model's own knowledge.

**Local tool cards** — certain questions skip the model entirely:
- Time and date queries hit the server clock and return a clock card instantly. The LLM never runs.
- Math, unit conversions, number bases, hex, hashing/encoding, tip splitting — all computed locally, shown as cards.
- Stock quotes and weather pull from configured APIs when available.

The reasoning: "what time is it in Tokyo?" has an exact answer that a model can't give (it doesn't know the current time) and a web search won't give either. The server clock does. These paths are dramatically faster than a model reply.

**Thinking indicator** — a slowly blinking "Thinking…" in the response position, formatted exactly like a real reply. Not a spinner (which implies a network request) or a progress bar (which implies a known completion time). Blinking text says the model is composing.

**Stop button** — while streaming, the send button becomes a stop square. Clicking it aborts the fetch; whatever text arrived is saved. Incomplete is better than nothing.

---

### Web search

An optional toggle in the composer toolbar. When on, the backend decides whether to actually search — the toggle is permission, not a guarantee.

The smart query classifier runs before any API call. Conversational greetings and short follow-ups are never searched (`"hey"` used to trigger five Tavily calls — this was an early bug I fixed fast). Time queries go to the clock path, not search. Only messages with genuine live-information signals (event language, "latest", time references, comparisons) trigger a search.

When search runs, the query may be rewritten into a cleaner search query first, and complex questions fan out into several parallel sub-searches. The `atelier_search` SSE event arrives before any model tokens and carries the actual query used, the provider, whether the result was cache-served, and source titles with URLs and publication dates. You can see what was searched and click through to the source.

Supports Tavily and Brave. Configure via `/setup search`.

---

### Memory

Every chat turn goes through an extraction job after it finishes streaming — never on the hot path, never blocking your reply. The extractor first scores the turn for significance using rules only (no model call). Low-significance turns are skipped entirely. Ambiguous turns ask the cheap model "is this worth extracting?" High-significance turns extract unconditionally.

Extracted facts are **structured atoms** — not text blobs. Each atom has a subject, predicate, predicate category, object, modality, confidence, and status. The structure is what makes the rest of the memory system possible.

**Reconciliation** runs before every write:
- Near-duplicate? Corroborate the existing atom instead of inserting a copy.
- Functional fact with a conflicting value? Supersede the old atom. Old value gets `status='superseded'`; new value is inserted as active. Both persist — the chain is walkable.
- Genuine conflict that can't be auto-resolved? Opens a question in the Review tab.

**Confidence decay** is computed at read time, never written to the database. There's no background job touching every atom. Facts score lower and lower as time passes without corroboration until they fall below the fading threshold. The formula has a grace period before decay starts, then exponential half-life decay by predicate category. Corroboration nudges the stored confidence up — facts that keep being mentioned resist decay.

**KNN retrieval** keeps an in-memory float32 matrix of all active atom embeddings. Cold build is ~220ms; warm cosine query is ~4ms. The cache invalidates on any mutation via a `memory_mutation_seq` counter — not just on row count change, so retractions and supersessions correctly evict dead atoms from the cosine space.

**The memory surface** has six tabs:
- **Overview** — recent activity, open questions count, goals, inferred knowledge card
- **Garden** — the full fragment list, grouped by strand, with modality glyphs and confidence display
- **Review** — conflict questions and stale-goal questions, each as a resolution card with four choices
- **Goals** — desire and plan atoms with close (achieved/dropped) buttons
- **Timelines** — strand lanes with atoms laid out chronologically
- **Inferred** — insight atoms and open hypotheses

**Strands** are emergent clusters — groups of thematically related atoms found by geometric label propagation over the KNN graph, running hourly. They're labeled by the cheap model. No manual categorization.

**Hypotheses** run weekly. The system generates up to three falsifiable predictions from patterns in the atom corpus. Hypotheses are never injected into chat context. They live in the Inferred tab only. When a new extracted atom confirms a hypothesis, it promotes to an insight. I was deliberate about this: speculative inference has no business being stated as fact in an answer.

**Background inference** runs periodically across the atom corpus, looking for patterns, implied preferences, and contradictions that span multiple facts. Every produced inference starts as `status='proposed'` and is invisible to retrieval until confirmed from the Review tab. Unconfirmed inference never enters chat context. This is the most important invariant in the whole memory system.

**Session warming** — when a new session starts, a background task predicts what you're likely to ask about by blending your previous session's messages, open goals, due commitments, time-of-day slot patterns, and project context into a composite query vector. The predicted retrieval block is stashed. If the first message in the session lands close enough (cosine ≥ 0.30), the stash is served instead of running a cold retrieval. If anything changed in memory since the stash was built, it's discarded and cold retrieval runs instead.

**Commitments** — when the model makes a promise in an assistant turn, it routes to the task table instead of the atom store. The chat context block includes a `[COMMITMENTS]` section with recent open commitments, so the model can't silently forget what it said it would do.

---

### Deep research

You ask a question; the system plans a research strategy, runs parallel web searches, synthesizes a sourced answer, and saves the report. Reports are searchable and show up as provenance chips in chat when relevant.

The pipeline works in rounds — after each round it checks for gaps and generates follow-up questions, going deeper where the topic warrants it. Minimum two rounds for anything substantive.

The answer is structured as individual **claims**, each:
- Tied to the sources that support it
- Checked against those sources for entailment
- Labeled: `supported` (two+ independent sources confirm), `single-source`, `disputed` (sources disagree), or `unverified`
- Shown with inline citation numbers linking to the exact source

Before searching, the system reads what you've already told it from memory, so answers can be grounded in your context.

The report can be read as normal prose (Read view) or as individual verified claim cards (Claims view). Neutral citations — sources consulted but not directly confirming — are shown with a different visual treatment so you can see exactly what counted and what didn't.

I went through several versions to get the verification to actually work. For a long time, `supported` (two+ independent sources) was theoretically possible but practically never reached — the writer kept citing only one source per claim, and "supported" requires two. I added a corroboration step that actively scans the gathered material for a second confirming source from a different website when only one was cited. Now it's reachable.

---

### MCP client

The app can act as an MCP client, connecting to external tool servers. Destructive tool calls go through an approval gate before executing.

---

## Architecture

Three-layer backend:

```
routers/      thin HTTP — request parsing, auth check, response shaping
services/     stateless async logic — only layer that touches the DB
workers/      background jobs registered with a SQLite-backed queue
```

Routers never import `sqlite3`. All DB access goes through `services/db.py` async helpers. The DB module enforces a single-writer model (one-thread executor) and an 8-thread reader pool. Writes that must be atomic go through `db.write(fn)`, running inside a transaction on the writer thread.

The database is `data/atelier.db` — a single SQLite file in WAL mode. The `sqlite-vec` extension handles vector operations. Schema is in `services/schema.sql` and applied idempotently on startup with safe `ALTER TABLE ADD COLUMN` migrations in try/except blocks.

Embeddings are 256-dimensional float32. Two backends: an OpenAI-compatible `/embeddings` endpoint (Ollama, LM Studio, llama.cpp) when configured, or a deterministic local hash-embedding fallback for offline use. The hash fallback is fast but cosine similarity is only meaningful for lexical overlap — semantic similarity between different words won't work correctly without a real model.

LLM routing uses two tiers: a cheap model for extraction, clustering labels, categorization, and inference, and the main model for chat responses and research synthesis. Task-to-tier mapping is configurable via `app_config`.

All colors come from `static/tokens.css` CSS custom properties. Two themes: `natural` (warm parchment) and `mono` (grayscale). Set via `data-theme` on `<html>`. Typography: Cormorant Garamond for display and response ledes, Lora for body text, IBM Plex Mono for UI labels and metadata. Loaded from Google Fonts.

---

## Test suite

**Fixture tests** (no server needed, each spins up a temp DB):
```bash
python -m scripts.test_clustering
python -m scripts.test_inference
python -m scripts.test_retrieval_modes
python -m scripts.test_intent
python -m scripts.test_surfacing
python -m scripts.test_commitments
```

**Full integration suite** (manages its own server process):
```bash
python -m scripts.run_tests           # all groups
python -m scripts.run_tests --group 3 # single group
```

Groups 1–3 are gating: p95 retrieval latency under 50ms, dominance cap, and scanned-PDF rejection.

**Latency benchmark** (server must already be running):
```bash
python -m scripts.bench
python -m scripts.bench --retrieval-only
```

The p95 latency target is < 50ms at 50k atoms + 3k document chunks. The KNN cache warms on startup as a background task; after warm-up, cosine queries run in ~4ms.
dex.md) for the full architecture and design rationale.
