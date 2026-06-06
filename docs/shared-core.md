# The Shared Core

*The architecture every feature plugs into. Written by Clay.*

---

## Why I built a core before building features

The thing I kept wanting was for the surfaces to *talk to each other*. Research should sharpen what chat knows. Notes should be able to pull what research found. Chat should remember what I told it last week. The naive way to get that is to wire each feature to each other feature — chat-to-memory, research-to-memory, notes-to-research — and you end up with a spaghetti of point-to-point connections that nobody can reason about.

So I didn't do that. Instead there's **one core**, and everything integrates through two shared pipelines:

- **Ingestion** — anything that produces text (chat turns, research findings, saved notes, email facts) flows through *one* path, becomes memory atoms, and gets embedded + indexed.
- **Retrieval** — anything that needs context (chat, the notes co-writer, drafts) calls *one* hybrid-search function over that same store.

Because every surface reads and writes the same core, the integrations happen for free. There is no "research → memory" connector. Research just writes atoms. Chat just reads them. That's the whole trick, and it's why I built the core (Phase 0) completely before I touched a single feature.

The code lives in `services/` (testable, no FastAPI imports) and `workers/` (background jobs). Routers in `routers/` stay thin — parse the request, call a service, shape the response. `app.py` is just wiring.

---

## The hot-path rules

These are latency invariants. I treat a violation as a bug, not a preference.

1. **Nothing blocks a user-facing reply except the model stream.** Extraction, embedding of new content, email sync, research, consolidation — all background jobs.
2. **Embeddings are local and cached by content hash.** Never a paid embedding API on the hot path; never re-embed identical text.
3. **Cheap/local model for the cheap work** (extraction, classification, card generation). The big model is only for the user-facing answer.
4. **Token budgets enforced in code.** Injected memory is hard-capped (~700 tokens by default); research breadth/depth are bounded constants.
5. **One reused `httpx.AsyncClient`** for the whole app lifespan. Stream all user-facing output over SSE.
6. **One serialized writer for SQLite** so concurrent PC + phone + background writes never hit "database is locked".

Everything below is in service of these six.

---

## 1. Storage — SQLite (WAL), one writer

`services/db.py`. I open every connection with:

```
PRAGMA journal_mode=WAL;     -- many readers + one writer, concurrently
PRAGMA synchronous=NORMAL;   -- safe with WAL, much faster than FULL
PRAGMA busy_timeout=5000;    -- wait instead of erroring on contention
```

The interesting decision is **how I guarantee a single writer**. I didn't hand-roll a queue with futures. I used a `ThreadPoolExecutor(max_workers=1)` as the write executor. One thread means one connection means writes are serialized by construction — submitting a write callable to that executor *is* the queue. Reads go through a separate small pool (`max_workers=4`); WAL lets them run while the writer writes. Each worker thread lazily opens its own connection (thread-local) with the pragmas and the sqlite-vec extension loaded.

This is the fix for the classic SQLite-under-concurrency failure, and I verified it: 400 overlapping writes (chat persistence + note autosave + task creation, all at once) produced **zero lock errors**. See [latency-testing.md](latency-testing.md).

The schema lives in `services/schema.sql` and is fully idempotent (`CREATE ... IF NOT EXISTS`), so it doubles as the migration runner — it runs on every startup and is a no-op once everything exists.

### The importer

The old app stored everything in `data/*.json`. On first startup `services/importer.py` reads those files, writes them into the tables, **verifies row counts**, and sets a `json_imported` flag so it never runs again. The JSON files are left on disk as a safety net but are no longer read. When I ran it, it reported `memory: 1, notes: 1, tasks: 1, research: 2, skills: 1` imported and verified — small because it was test data, but the path is proven.

### Things I considered and didn't do
- **A heavier ORM / SQLAlchemy.** For a single-file local DB with a thin repository layer, an ORM is pure overhead. Raw SQL in `services/` is fine and fast.
- **WITHOUT ROWID tables.** I rely on the implicit integer `rowid` to key the vec0 and FTS5 virtual tables back to each atom, so I kept normal rowid tables.

---

## 2. Embeddings — local-first, cached

`services/embeddings.py`. The contract is `embed(text) -> vector`, with an `embedding_cache(content_hash, vector, model)` table so identical text is never embedded twice. Text is normalized (lowercased, whitespace-collapsed) before hashing.

There are two backends behind that one function:

1. **An OpenAI-compatible `/embeddings` endpoint** when one is configured (`embedding_model` in app_config). This is the spec's "use the local LLM server's embeddings endpoint" option — Ollama / llama.cpp / LM Studio — so I don't have to stand up extra infra.
2. **A deterministic local hashing embedding** (the feature-hashing trick) as the default. It captures lexical overlap, runs in microseconds, needs no model download, and works fully offline. That last property is exactly what makes it the right tool for the scaling benchmark.

Everything is projected to a fixed **256 dimensions** (Matryoshka-style truncate + renormalize) and L2-normalized, so the vector tables stay fixed-width and cosine behaves no matter which backend produced the raw vector.

### What I deferred
- **EmbeddingGemma-300M via onnxruntime** — the spec's first option. It's a model download plus a runtime, and the endpoint path already satisfies "real local embeddings." The backend is swappable behind `embed()`, so dropping Gemma in later is a one-file change.
- **int8 quantization of stored vectors.** The spec suggested storing int8. I store float32 at 256 dims. I left int8 as the *first* scaling lever — and then the Part 4 test showed the vector scan wasn't the bottleneck anyway (14ms for 50k), so I didn't need it. Measuring beat guessing.

---

## 3. Retrieval — one hybrid function

`services/retrieval.py`. `retrieve(query, k, budget_tokens) -> [atoms]` is the single entry point that serves chat, the co-writer, and drafts. The pipeline:

```
embed query
  → vector top-K (sqlite-vec vec0)   ┐ run concurrently
  → keyword hits (FTS5)              ┤ over the WAL read pool
  → pinned atoms (always included)   ┘
  → fuse with Reciprocal Rank Fusion
  → recency boost (30-day half-life)
  → trim to the token budget
```

- **Vectors** live in a `vec0` virtual table (`float[256]`, cosine). The KNN `LIMIT` has to sit in a subquery *directly* on the vec table — if you `JOIN` first and `LIMIT` the outer query, sqlite-vec can't see the constraint and errors out. That cost me one debugging round.
- **Keywords** live in an FTS5 table. I strip stopwords from the FTS query because ultra-common words ("the", "and", "what") match a huge fraction of rows and blow up the bm25 ranking — that was a real measured cost (~55ms → negligible at 50k). The vector side covers semantics anyway.
- **RRF** fuses the two ranked lists without needing comparable score scales (the usual headache with hybrid search). Pinned atoms bypass ranking entirely and float to the top.

I parallelized the three independent reads with `asyncio.gather`. That, plus the stopword fix, took retrieval from ~120ms p95 down to ~49ms p95 at 50k atoms — comfortably under the 80ms budget.

---

## 4. Background jobs

`workers/jobs.py`. A `jobs(id, type, status, payload, attempts, last_error, …)` table, a couple of worker tasks consuming queued jobs, and APScheduler for the periodic ones (consolidation, email poll).

- **Atomic claim.** A worker claims a job with an `UPDATE … WHERE status='queued'` that runs through the single writer, so two workers can never grab the same job — the serialized writer gives me the atomicity for free.
- **Restart-safety.** On startup, anything left `running` (because the process died mid-job) is requeued.
- **Retries.** Failed jobs requeue up to `MAX_ATTEMPTS`, then land in `error` with the message.
- **Timing.** Every job records `duration_ms` and `queue_wait_ms`. That feeds the metrics (Part 4) and lets me watch queue depth under load.

Handlers register themselves with a decorator (`@jobs.register("extract_memory")`), and importing the worker module is what registers it — `app.py` imports them at startup.

---

## 5. The shared HTTP client

`services/http_client.py` holds one `httpx.AsyncClient`, created in the lifespan handler and reused everywhere — chat streaming, embeddings, model probing, research fetches. A client-per-request means a new TLS handshake and no connection reuse every time, which is a real and pointless latency tax. There's exactly one, and it's closed on shutdown.

`services/llm.py` sits on top of it with two tiers: `complete()` (big model, for synthesis and drafts) and `cheap()` (the configured cheap model, for extraction / classification / card generation). That's hot-path rule 3 expressed in code.

---

## 6. Access & secrets

`services/auth.py`, `services/crypto.py`.

- **Auth is opt-in.** The mechanism is built — shared-secret login that issues a signed, timed session cookie (itsdangerous), and middleware that gates every `/api` route except login and the public share route. But it's *off* by default, because the whole point of "keep `127.0.0.1` until auth exists" is that the local single-user experience needs zero setup. Set `ATELIER_AUTH=1` (plus a secret) the day I bind to the LAN or put it behind a Tailscale/Cloudflare tunnel.
- **CORS is locked** to real origins (`127.0.0.1:8000`, `localhost:8000` by default, configurable). Never `*` with credentials.
- **Endpoint API keys are encrypted at rest** with Fernet. The key is derived from `ATELIER_SECRET` (a passphrase, so blobs are portable across machines) or, failing that, a generated key stored in `data/.fernet.key`. Keys are decrypted only in-process to build request headers and are **never** returned to the client — the config endpoint returns `has_key: true`, never the key itself. This directly fixes the old incident where keys lived in a JSON file (see [repository.md](repository.md)).

---

## 7. Instrumentation

`services/metrics.py` + the timing middleware in `app.py`. This is built in Phase 0 on purpose, so every later phase is measurable. Details and results are in [latency-testing.md](latency-testing.md), but the design choice worth recording here: per-request timings go into **in-memory rolling buffers**, not a DB write per request. Writing a row on every request would amplify writes on the hot path and pollute the very metric I'm trying to read during a benchmark. A periodic flush persists samples for durability; `/api/metrics` reads the buffers for instant p50/p95/p99.

---

## The backend file map

```
app.py                  # lifespan, middleware, router mounting, static
services/
  db.py                 # WAL, single-writer executor, async read/write helpers
  schema.sql            # idempotent schema = migration runner
  importer.py           # one-time JSON → SQLite, with verification
  embeddings.py         # embed() + content-hash cache
  retrieval.py          # the one hybrid retrieve()
  memory.py             # atom repository (atom + vec + fts in one txn)
  config.py             # endpoints + app_config, encrypted keys
  crypto.py             # Fernet encryption
  auth.py               # opt-in shared-secret sessions
  http_client.py        # the one AsyncClient
  llm.py                # complete() / cheap()
  metrics.py            # rolling buffers + percentiles
  search.py             # SearXNG → DuckDuckGo → page fetch
  research.py, notes.py, tasks.py, skills.py, files.py, flashcards.py, email.py, mcp.py
workers/
  jobs.py               # queue, worker loop, scheduler, atomic claim
  extraction.py         # memory extraction + consolidation
  research.py           # the deep-research pipeline
  cards.py, cowriter.py, email.py
routers/                # thin HTTP layer, one module per surface
scripts/
  seed_memory.py        # N synthetic atoms for the scaling test
  bench.py              # latency + concurrency harness
```
