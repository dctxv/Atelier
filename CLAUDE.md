# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Run the server:**
```bash
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

**Run a specific fixture test (no server needed — spins up its own temp DB):**
```bash
python -m scripts.test_clustering
python -m scripts.test_inference
python -m scripts.test_retrieval_modes
python -m scripts.test_intent
python -m scripts.test_surfacing
python -m scripts.test_commitments
```

**Run the full integration test suite (manages its own server process):**
```bash
python -m scripts.run_tests           # all 9 groups
python -m scripts.run_tests --group 3 # single group
```
Groups 1–3 are **gating** (p95 latency, dominance cap, scanned-PDF rejection). The suite starts/stops a real server and requires no running instance.

**Run the latency benchmark (server must already be running):**
```bash
python -m scripts.bench
python -m scripts.bench --retrieval-only
```

**Install dependencies:**
```bash
pip install -r requirements.txt
```

## Architecture

### Three-layer backend

```
routers/      thin HTTP — request parsing, auth check, response shaping
services/     stateless async logic — the only layer that touches the DB directly
workers/      background jobs registered with workers/jobs.py queue
```

Routers never import `sqlite3`; all DB access goes through `services/db.py` async helpers (`fetchone`, `fetchall`, `execute`, `write`). The DB module enforces a single-writer model (one-thread `ThreadPoolExecutor`) and an 8-thread reader pool. Every write that must stay atomic goes through `db.write(fn)`, which runs inside a transaction on the writer thread.

### Frontend — no build step

`static/index.html` loads React 18 + Babel from `/lib/` (local files), then fetches each JSX in a fixed sequential order:
```
components.jsx → shell.jsx → chat.jsx → memory.jsx → notes.jsx →
research.jsx → setup.jsx → app.jsx (root)
```
Each file is `Babel.transform()`-compiled and `eval()`-d in order. Files export through `window` (e.g. `window.V2Chat = { ChatSurface }`). **No bundler, no npm, no build step.** Cache-bust by bumping the `?v=YYYYMMDD` query string in `index.html` after any JSX change.

All colors come from `static/tokens.css` CSS custom properties — never hardcode hex in JSX. Both themes (`natural` / `mono`) are set via `data-theme` on `<html>`. Typography: Cormorant Garamond (display/lede), Lora (body), IBM Plex Mono (UI labels).

### Storage

Single SQLite file at `data/atelier.db`. WAL mode. `sqlite-vec` extension loaded on every connection for vector operations. Schema is in `services/schema.sql`; `db.init_db()` applies it idempotently and runs `ALTER TABLE ADD COLUMN` migrations in try/except blocks (safe to re-run on startup). All timestamps are integer epoch seconds from `db.now()`. Embedding vectors are 256-dimensional float32 (`EMBED_DIM = 256`), stored as blobs and as virtual `vec0` shadow tables.

### Embeddings

`services/embeddings.embed(text)` — two backends:
1. An OpenAI-compatible `/embeddings` endpoint (Ollama / LM Studio / llama.cpp) when `embedding_model` + `embedding_endpoint_id` are configured.
2. Deterministic local hash-embedding fallback (`_local_embed`) — fast, offline, but cosine similarity is only meaningful for lexical overlap. **The synonym-dedup gate in clustering is disabled under the hash fallback** (`_using_real_embeddings()` returns False); label merge is unreliable without a real model.

All embeddings are cached by `(model, normalized_text)` hash in `embedding_cache`.

### LLM routing

`services/llm.py` provides two tiers:
- `cheap()` / `cheap_strict()` — uses `cheap_model` config (cheap/local model)
- `complete()` — uses `active_model` config (main model)

`_DEFAULT_TASK_TIERS` maps task names to tiers; overridable via `task_tiers` in `app_config`. Every call writes token usage to `usage_daily`.

### Memory system

Atoms are `memory_atom` rows with structured fields: `subject / predicate / predicate_category / object / modality / confidence / status`. Status values: `active | superseded | retracted | archived`. Only `active` (and legacy `NULL` status) atoms enter the KNN retrieval matrix.

Key invariants:
- **Visibility Law**: derived/inferred atoms start as `status='proposed'` and are invisible to retrieval until confirmed. Never inject unconfirmed inference into chat context.
- **Confidence decay** is computed at read time in `retrieval._effective_confidence()` — never written to the DB. Atoms below 0.4 effective confidence are "fading".
- Every mutation calls `db.bump_mutation_seq()`, which invalidates the in-memory KNN cache (version stamp is `(COUNT, MAX_rowid, mutation_seq)`).
- Supersession chains are walkable; nothing is ever hard-deleted from the atom history.

The retrieval KNN cache (`services/retrieval.py`) holds all active atom vectors as a numpy float32 matrix (~51 MB at 50k atoms). Cold build is ~220 ms; warm cosine query is ~4 ms. The cache is pre-warmed on startup as a background task.

### Background jobs

`workers/jobs.py` — SQLite-backed queue with 2 worker tasks and APScheduler for periodic work. Register a handler with `@jobs.register("job_type")`. Enqueue with `jobs.enqueue("job_type", payload)`. Periodic jobs are registered in each worker module's `register_schedule()`, called from `app.py` lifespan.

Active periodic workers:
| Worker | Cadence | Purpose |
|---|---|---|
| `workers/extraction.py` | after each chat turn | extract memory atoms from conversation |
| `workers/clustering.py` | hourly + weekly full | emergent strand clustering |
| `workers/memory_inference.py` | periodic | W2 corpus-level inference |
| `workers/memory_prescient.py` | weekly/quarterly | hypotheses, drift analysis |
| `workers/weekly_diff.py` | weekly | narrative diff summary |
| `workers/email.py` | periodic | email poll |

### Clustering / strands

`services/clustering.py` — pure geometric core: `normalize_rows`, `build_knn_graph`, `deterministic_label_propagation`, `communities`. No DB access.

`workers/clustering.py` — all DB-aware logic: full vs. incremental pass decision, carry-over pending pool (`cluster.pending_pool` config key), stale strand cleanup, label dedup gate. Key config knobs: `cluster.knn_k`, `cluster.sim_threshold`, `cluster.min_cluster_size`, `cluster.max_pool_size`, `label.merge_threshold`.

`services/strands.py` — strand registry CRUD. `apply_clustering_result()` is the single write path for clustering output.

### Fixture tests

`scripts/test_clustering.py` (and its siblings) use `db.configure_for_tests(path)` to redirect all DB access to a temp file before calling `db.init_db()`. Call `db.shutdown()` in a `finally` block. These tests never touch `data/atelier.db`. They can be run without the server.

## Key configuration knobs

Settings live in `app_config` table (key/value). Access via `config.get_setting(key)` / `config.set_setting(key, value)`. The worker helpers use `_cfg(key, default)` which coerces type from the stored string.

Values tagged `# [VALIDATE]` in the code indicate thresholds that have not yet been validated against a real 50k-atom corpus and may need tuning. `bench.py` is the tool for retrieval latency validation; the p95 target is < 50 ms at 50k atoms + 3k doc chunks.

## What's deferred / not built

See `docs/v2-deferred.md` for the full list. Notable gaps relevant to current work:
- `merge_threshold = 0.80` for label synonym-dedup is geometrically correct but **not validated against real synonym pairs** under a production embedding model (e.g. "Career"/"Work" cosine). Open verification item.
- Drift-triggered strand relabeling is not implemented (existing strands always copy their old label on centroid match; the spec called for relabel-on-drift).
- Manual strand reassignment from the UI is out of scope for the current pass.
- No browser test harness exists — frontend changes are verified by manual checklist, not automated tests.
