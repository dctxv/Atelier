# Atelier GPT-5.5 Project Handoff Report

Generated on 2026-06-23 from the current `C:\Atelier` checkout.

This report is for GPT-5.5 or another senior AI collaborator being asked to
propose new ideas and features for Atelier. It is intentionally practical: it
describes what the app actually does now, what design constraints matter, where
the code is strong, where it is partial, and which directions are likely to
compound rather than fight the existing system.

It is based on direct code inspection and non-invasive verification. Do not
assume README/build-summary claims are newer than this file.

## Verification Performed

Commands that passed:

```powershell
python -m compileall app.py services routers workers scripts
python -m scripts.test_intent
python -m scripts.test_retrieval_modes
python -m scripts.test_clustering
python -m scripts.test_intake_discipline
```

Commands deliberately not run:

```powershell
python -m scripts.run_tests
python -m scripts.test_inference
```

Reason: the full runner and older inference test use the live app database or
can create substantial live state. The newer clustering and intake tests use
temporary SQLite databases and are safer for handoff verification.

## One-Paragraph Summary

Atelier is a local-first AI workspace: FastAPI, SQLite, `sqlite-vec`, and a
buildless React 18 frontend served from `static/`. The app is best understood as
a single-user AI cockpit, not a SaaS product. Its deepest implemented systems
are chat, hybrid retrieval, structured memory, document ingestion, projects,
deep research, and background jobs. The most recent work adds emergent memory
strand clustering and memory-intake discipline: high-confidence stated facts can
skip the review queue, inferences are throttled and deduplicated, stale
low-confidence unreviewed facts can soft-retire, and memory strands are now
geometry-derived rather than seeded from a static taxonomy. Several advertised
areas remain backend-only or UI-incomplete, especially Files, Flashcards, Email,
and MCP tooling.

## Product Shape

Atelier is not trying to be a general chat clone. It is closer to a local
personal operating room for AI work:

- Chat is the primary working surface.
- Memory is structured, reviewable, and used by retrieval.
- Documents and projects add scoped workspace context.
- Research performs multi-step web-assisted synthesis.
- Notes, tasks, scratchpad, skills, and commitments provide lightweight
workspace surfaces around the chat core.
- Some systems are experimental plumbing rather than polished product surfaces.

The design should preserve local-first assumptions:

- One trusted local user.
- Local SQLite as source of truth.
- Background jobs for slow or model-heavy work.
- Retrieval and chat response paths should remain bounded and explainable.
- User-facing memory should expose uncertainty instead of pretending every atom
is neatly categorized.

## Current Runtime State In This Checkout

The live database is `data/atelier.db`.

Read-only snapshot observed during this handoff:

- Memory atoms: 22 total, 21 active, 1 superseded.
- Active memory atoms assigned to a strand: 0.
- Active memory atoms with `strand_id IS NULL`: 21.
- Dirty memory atoms awaiting clustering: 22.
- Memory strand rows: 0.
- Sessions: 12.
- Projects: 1.
- Documents: 1.
- Files: 4.
- Notes: 3.
- Tasks: 1.
- Research jobs: 10.
- Research sources: 114.
- Research chunks: 1154.
- Claims: 152.
- Embedding cache rows: 2053.
- Usage daily rows: 20.

Relevant current config observed:

- `active_model`: `z-ai/glm-5.2`.
- `cheap_model`: `deepseek/deepseek-v4-flash`.
- `embedding_model`: unset, so embeddings fall back to `local-hash-v1`.
- `memory.tier_selected`: `true`.
- `memory.tier`: `basic`.
- `cluster.last_knn_version`: unset.
- `cluster.pending_pool`: unset.

Important interpretation:

- The Memory UI's "Unsorted" state means `memory_atom.strand_id IS NULL`.
- In this live DB, all active memories are currently Unsorted because no
  clustering result has been persisted yet.
- Missing cheap-model labels would create unlabeled strands, not Unsorted atoms.
  Zero `memory_strands` rows means clustering assignment itself has not landed.

## Entry Point And Startup

Main file: `app.py`.

Startup behavior:

- Creates one shared `httpx.AsyncClient`.
- Initializes SQLite through `services/db.py`.
- Runs importer/migrations.
- Warms the memory KNN cache in the background.
- Registers scheduled jobs:
  - memory extraction/consolidation/pruning/calibration
  - email polling
  - memory inference
  - prescient memory passes
  - memory clustering
  - weekly diff
- Starts the job worker.
- Runs strand bootstrap, which is now intentionally a no-op.
- Mounts API routers.
- Serves the React frontend from `static/`.

Included routers:

- auth
- config
- chat
- memory
- notes
- tasks
- files
- documents
- projects
- research
- sessions
- skills
- flashcards
- cowriter
- email
- MCP
- search
- web
- metrics
- scratchpad

Authentication:

- Optional by default.
- Localhost can run without auth.
- `ATELIER_AUTH=1` enables shared-secret style auth.
- Public file shares at `/share/{token}` intentionally bypass API auth.

## Tech Stack

Backend:

- Python FastAPI.
- SQLite with WAL mode.
- `sqlite-vec` for vector tables.
- FTS5 for memory and document full-text search.
- `httpx` for providers/model calls.
- APScheduler-style periodic jobs through the local job system.
- Fernet encryption for local secrets.

Frontend:

- React 18 and ReactDOM are served from local static assets.
- Babel standalone transpiles JSX in browser.
- There is no Vite/Webpack/build pipeline.
- KaTeX, Cytoscape, and Mermaid are loaded externally.

Consequence:

- Iteration is simple, but frontend syntax errors can surface at runtime.
- Browser smoke tests would be valuable because there is no compile-time frontend
  guardrail.

## Repository Map

Top-level paths:

- `app.py`: FastAPI entry point and router mounting.
- `services/`: repositories, core logic, config, retrieval, memory, search.
- `routers/`: HTTP API layers.
- `workers/`: background jobs and schedulers.
- `static/`: React UI and browser assets.
- `scripts/`: tests, smoke suites, benchmark and seed helpers.
- `docs/`: feature/design notes; useful but not always current.
- `data/`: live runtime state.

Important storage:

- SQLite DB: `data/atelier.db`.
- Uploads: `data/uploads`.
- Schema source: `services/schema.sql`.
- Runtime migrations: `services/db.py`.

## Database And Storage Model

The schema is idempotent and still evolves on startup. `services/schema.sql`
contains baseline tables, while `services/db.py` applies additive migrations.

SQLite behavior:

- WAL mode.
- Single writer queue.
- Multiple reader workers.
- `sqlite-vec` loaded per connection.
- Embedding dimension: 256.

Major table groups:

- Chat: `session`, `message`.
- Memory: `memory_atom`, `memory_vec`, `memory_fts`, `memory_event`,
  `memory_question`, `memory_strands`.
- Documents: `file`, `share_link`, `document`, `document_chunk`,
  `document_chunk_vec`, `document_chunk_fts`.
- Research: `research`, `research_section`, `research_source`,
  `research_chunk`, `research_chunk_vec`, `research_meta`, `claim`,
  `claim_evidence`, `entity`, `relation`.
- Notes/tasks: `note`, `task`, `commitment`.
- Flashcards: `deck`, `card`, `review_log`.
- Email: account/message tables.
- MCP: server config/log tables.
- Jobs/metrics/config: `jobs`, `usage_daily`, `app_config`, provider metrics.
- Projects: `project` plus `project_id` columns added to documents, memory,
  and sessions.

## Model And Embedding Behavior

The app assumes OpenAI-compatible chat and embedding endpoints.

LLM helpers:

- `llm.complete()` uses `active_model`.
- `llm.cheap()` uses `cheap_model` if configured, otherwise falls back to
  `active_model`.
- `llm.cheap_strict()` requires an explicit `cheap_model` and never falls back
  to the active model.

Current strict-cheap usage:

- Memory strand labeling uses `cheap_strict()`.
- Memory inference now uses `cheap_strict()`.

Known cost-ceiling caveat:

- Several older background features still call `llm.cheap()`, so they can fall
  back to the active model if no cheap model is configured. This is a latent
  cost-control issue in prescient memory, research planning/gap checks, document
  abstracts, card generation, email categorization, project librarian, and other
  paths.

Embeddings:

- Preferred: configured OpenAI-compatible `/embeddings` endpoint via
  `embedding_endpoint_id` and `embedding_model`.
- Fallback: deterministic local feature-hash embedding named `local-hash-v1`.
- All embeddings are projected/truncated/padded to 256 dimensions and
  normalized.

Important limitation:

- The local hash embedding is fast and offline but lexically shallow. Retrieval,
  clustering, label-merge dedup, and semantic grouping work much better with a
  real embedding model.

## Frontend Surfaces

Main files:

- `static/index.html`
- `static/app.jsx`
- `static/shell.jsx`

Left rail navigation currently includes:

- Chat
- Projects
- Research
- Memory
- Notes
- Scratchpad
- Tasks
- Documents
- Files
- Settings

Implemented first-class frontend surfaces:

- Chat
- Projects
- Research
- Memory
- Notes
- Scratchpad
- Tasks
- Documents
- Settings

Still placeholder or backend-only:

- Files: the shell advertises it, but `static/app.jsx` has no `case 'files'`.
  It falls through to the generic "coming soon" placeholder.
- Flashcards: backend exists, no visible first-class UI in the main nav.
- Email: backend exists, no visible first-class UI.
- MCP tools: backend exists, no visible management/tool-use UI.

## Chat System

Main files:

- `routers/chat.py`
- `services/sessions.py`
- `services/retrieval.py`
- `services/intent.py`
- `services/local_tools.py`
- `static/chat.jsx`

Capabilities:

- SSE streaming from `/api/chat/stream`.
- Persists sessions and messages in SQLite.
- Supports global and project-scoped chats.
- Can migrate older localStorage chat history.
- Injects memory and document context according to retrieval policy.
- Adds project instructions, project manifests, whole-file snippets, open
  commitments, and enabled skills when applicable.
- Emits provenance/debug trace events when enabled.
- Enqueues memory extraction after turns, including on abort/interruption paths.

Local deterministic tools:

- Time/date.
- Math/unit expressions.
- Time zone difference.
- Base conversion.
- Hashing.
- Base64 and URL encode/decode.
- Color conversion.
- Tip/split calculator.
- Weather and stock cards if provider keys are configured.

Web search behavior:

- Chat does not browse automatically.
- User must enable search.
- Intent classification then decides if web is useful.
- Search suggestions can be emitted when a current query appears but search is
  off.

Known chat limitations:

- No active endpoint/model means normal chat cannot answer.
- Some deterministic card-only answers can appear in the UI without persisting a
  normal assistant message. Reload may lose those card-only responses.
- Tooling is heuristic/local rather than a robust model-planned tool loop.

## Retrieval System

Main file: `services/retrieval.py`.

Retrieval combines:

- Memory vector KNN from a warmed in-memory NumPy matrix.
- Memory FTS.
- Document vector KNN through `sqlite-vec`.
- Document FTS.
- Pinned memory atoms.
- Project-scoped memory/docs when `project_id` is present.

Fusion:

- Reciprocal rank fusion style scoring.
- Memory recency boost.
- Read-time confidence decay.
- Document dominance cap.
- Token budget trimming.

Modes:

- `tool`
- `no_context`
- `factual`
- `technical`
- `exploratory`
- `personal`

Important policies:

- Tool and no-context modes suppress ambient memory.
- Technical mode suppresses personal-flavored memory.
- Pinned atoms are protected.
- Project context can force context even when a generic prompt would suppress it.
- Proposed/rejected inferences and hypotheses are excluded from chat retrieval.

New support for clustering:

- `memory_knn_snapshot(copy=True)` returns an atomic snapshot of the active memory
  matrix, atom ids, and KNN version for background clustering.

Verified:

- `scripts.test_retrieval_modes` passed 28/28 classification cases.

## Memory System

Main files:

- `services/memory.py`
- `routers/memory.py`
- `workers/extraction.py`
- `workers/memory_inference.py`
- `workers/memory_prescient.py`
- `workers/clustering.py`
- `services/clustering.py`
- `services/strands.py`
- `static/memory.jsx`

Memory atoms contain:

- Text.
- Type.
- Salience.
- Source kind/id.
- Project scope.
- Structured subject/predicate/object fields.
- Predicate category.
- Polarity/intensity.
- Modality.
- Confidence.
- Temporal validity fields.
- Status.
- Metadata JSON.
- Pinned flag.
- Strand assignment fields: `strand_id`, `strand_assigned_at`,
  `cluster_dirty`.

Statuses in active use:

- `active`
- `proposed`
- `rejected`
- `retracted`
- `superseded`
- `archived`
- `retired`

Important semantic split:

- Stated facts are inserted active immediately.
- The review queue for stated facts is not a retrieval gate. It is
  post-hoc cleanup: active chat facts without `meta.reviewed`.
- Derived inferences are inserted as `status='proposed'`,
  `modality='insight'`, `type='inference'`.
- Proposed inferences are not retrievable until confirmed.

Memory operations:

- Add/update/delete.
- Forget/retract.
- Supersede.
- Corroborate.
- Pin/unpin.
- Search.
- Review accept/reject.
- Provenance.
- Questions/tensions.
- Events/timeline.
- Inferences and proposed insights.
- Hypotheses and prescient behavior.
- Emergent strands and graph/garden views.

### Memory Extraction

Extraction file: `workers/extraction.py`.

Behavior:

- Runs after chat turns, never on the chat reply hot path.
- Uses a rule-based significance score first.
- Ambiguous turns may call the cheap model for yes/no significance.
- Extracts structured facts with cheap model.
- Reconciles duplicates and retractions before insert.
- Supersedes old functional/comparative facts when needed.
- Routes commitments to review-gated commitment objects.
- Can test prescient hypotheses if the memory tier is prescient.

Recent intake discipline:

- High-confidence non-sensitive stated facts from chat can auto-mark
  `meta.reviewed=true`.
- Auto-confirm writes a normal `reviewed` memory event with `reason='auto'`.
- Sensitive categories default to health, relationships, finances.
- Sensitive facts stay visible in the review queue even when high confidence.
- Auto-confirm does not make facts more retrievable because stated facts were
  already active; it only reduces review burden.
- Low-confidence old unreviewed stated facts can be soft-retired by the daily
  `prune_memory_review_queue` job.
- Pruning uses status `retired`, preserves the row/vector/audit trail, sets
  `cluster_dirty=1`, and relies on clustering cleanup to clear stale strands.

### Memory Inference

Inference file: `workers/memory_inference.py`.

Behavior:

- Corpus-level `infer_memory` reasons across active stated facts.
- Per-turn `infer_turn` reads implied-but-not-said signals after extraction.
- All new inferences are proposed, not active.
- `memory.add_inference()` deduplicates against proposed and active insight
  atoms using exact structured match and vector similarity.
- Duplicate inferences corroborate existing ones by increasing confidence,
  salience, `meta.sightings`, `last_used_at`, and provenance.
- Current thresholds are config-backed with `intake.*` knobs.

Recent throttle:

- `infer_turn` now requires distinct evidence sources before any model call.
- Distinct means `(source_kind, source_id)` when `source_id` exists, so multiple
  atoms from one chat turn count as one source.
- Per-pass proposal budget uses `intake.inference_budget`.
- Inference calls use `cheap_strict()` and fail closed without cheap model.

### Emergent Memory Strands

Core files:

- `services/clustering.py`: deterministic kNN graph construction and label
  propagation.
- `workers/clustering.py`: scheduled clustering worker.
- `services/strands.py`: persistent strand registry and assignment persistence.

Design:

- Single `strand_id` per atom for v1.
- No static taxonomy is seeded on cold start.
- `NULL strand_id` is the honest unassigned/noise state and appears in UI as
  "Unsorted".
- Strands are derived from active memory embeddings, not from predicate rules.

Worker behavior:

- Hourly incremental clustering job.
- Weekly full rebuild job.
- Full pass runs kNN graph clustering over all active atoms.
- Incremental pass assigns dirty active atoms to existing centroids when
  possible.
- Leftovers accumulate in `cluster.pending_pool`, allowing a strand to
  crystallize when enough similar atoms arrive across multiple passes.
- Full rebuild resets the pending pool.
- Stale strand cleanup nulls assignments for suppressed or non-active atoms.
- Labeling uses `cheap_strict()` and fails closed if no cheap model exists.
- Without a real embedding model, label synonym merge is intentionally limited
  because local hash vectors are not semantic.

Config knobs:

- `cluster.knn_k`
- `cluster.sim_threshold`
- `cluster.min_cluster_size`
- `cluster.max_runtime_ms`
- `cluster.block_size`
- `cluster.max_iter`
- `cluster.max_pool_size`
- `cluster.drift_threshold`
- `label.merge_threshold`
- `label.sample_size`

Verified by temp DB fixture:

- Migrations are idempotent.
- `add_atom` marks atoms dirty.
- Public KNN snapshot works.
- Full clustering is deterministic.
- Dirty updates re-enter cadence pass.
- Suppressed/non-active atoms get `strand_id` nulled.
- Incremental pending pool can crystallize new strands.
- Pool atoms can later be absorbed into matching centroids.
- Full rebuild preserves stable assignments where geometry supports it.
- Label dedup merges near-synonyms under controlled fixture geometry.

Open validation item:

- `label.merge_threshold=0.80` still needs measurement against a real embedding
  model, especially for pairs like Career/Work.

### Prescient Memory

Main file: `workers/memory_prescient.py`.

Capabilities:

- Hypothesis generation.
- Hypothesis testing against new facts.
- Confirmation/refutation paths.
- Suppression topics.
- Drift analysis.
- Stale-goal review questions.

Reality:

- This is experimental.
- It still calls `llm.cheap()` in several places, so it may fall back to active
  model if no cheap model is configured.
- Hypotheses are excluded from retrieval.

## Documents And RAG

Main files:

- `routers/files.py`
- `routers/documents.py`
- `services/files.py`
- `services/documents.py`
- `workers/documents.py`
- `static/documents.jsx`

Supported uploads:

- TXT.
- Markdown.
- Text-layer PDF.
- DOCX.

Flow:

- File bytes are stored under `data/uploads`.
- File row is created.
- Supported file types create a document row and enqueue `ingest_document`.
- Worker extracts text.
- Text is chunked around 1000 characters with overlap.
- Chunks get FTS and vector rows.
- Cheap model may generate an abstract.
- Document status becomes `ready` or `failed`.

Limitations:

- No OCR for scanned PDFs.
- No document viewer.
- No chunk management UI.
- Deleting document rows and deleting file rows are separate layers.
- Cleanup symmetry around file/document deletes should be tested more deeply.

## Projects

Main files:

- `services/projects.py`
- `routers/projects.py`
- `static/projects.jsx`

Capabilities:

- CRUD projects.
- Project-scoped chat sessions.
- Project-specific instructions.
- Project document upload.
- Assign existing documents to projects.
- Project-scoped memory atoms.
- Promote project memory to global.
- Project manifest injection into chat.
- Whole-file/librarian path for explicit file needs.
- Working-set cache for full file context in a session.

Important behavior:

- Project instructions override global persona inside project chat.
- Project docs/memory are scoped to the project.
- Global chat excludes project-only docs/atoms.
- Deleting a project disassociates documents, memory, and sessions by setting
  `project_id=NULL`; it does not delete those artifacts.

Known limitations:

- Manifest query ranking has a branch for query vector scoring, but abstract
  similarity is still stubbed at `0.0`.
- The project librarian uses `llm.cheap()`, so it can fall back to active model.
- Some UI copy still implies project conversations/memory are removed, but
  backend currently disassociates them.
- Removing a project document deletes the document row rather than merely
  unassigning it.

## Deep Research

Main files:

- `workers/research.py`
- `routers/research.py`
- `services/research.py`
- `static/research.jsx`

Workflow:

- User starts a research job with query and depth preset.
- Worker retrieves workspace/personal context.
- Cheap model plans subquestions.
- Search providers gather pages.
- Pages are chunked, embedded, deduplicated, and ranked.
- Active model synthesizes report sections/claims.
- Cheap model verifies claims using NLI-style checking.
- Entities and relations are extracted.
- Results persist to research tables.
- SSE streams live progress from an in-memory progress store.

Limitations:

- Requires configured search providers and model endpoints.
- Search quality depends heavily on provider availability.
- DuckDuckGo fallback is unofficial and brittle.
- Synthesis JSON can fail and fallback may be sparse.
- Live progress is in-memory and does not survive restart cleanly.
- Claim verification is model-assisted, not ground truth.
- Docs/comments may imply automatic memory promotion from research, but no clear
  automatic trusted-memory promotion was found.

## Search And Web

Main files:

- `services/search/`
- `routers/search.py`
- `routers/web.py`

Providers:

- Tavily.
- Brave.
- SearXNG.
- DuckDuckGo HTML fallback.

Capabilities:

- Provider ordering.
- Encrypted provider keys.
- Freshness classification.
- Recency-aware cache TTL.
- Search cache.
- Provider usage metrics.
- Page extraction/enrichment.
- Reranking and deduplication.

Limitations:

- Tavily/Brave require keys.
- SearXNG requires configured instance.
- DuckDuckGo fallback can be rate-limited or break.
- Chat only uses web when user toggles search and intent allows it.

## Notes And Co-writer

Main files:

- `services/notes.py`
- `routers/notes.py`
- `routers/cowriter.py`
- `workers/cowriter.py`
- `static/notes.jsx`

Capabilities:

- Notes CRUD.
- Autosave editor.
- Markdown preview.
- Selection-based co-writing: continue, rewrite, tighten.
- Co-writer streams output and can use workspace retrieval.

Known current bugs:

- Create-note contract mismatch remains. Backend returns `{ok: true, note: ...}`,
  while frontend treats the whole JSON response as the note object.
- Frontend calls `POST /api/notes/{id}/pin`, but no matching route exists.
- Saved notes should not be assumed to enter memory automatically.
- Co-writing requires active model.

## Tasks And Commitments

Main files:

- `services/tasks.py`
- `routers/tasks.py`
- `services/commitments.py`
- `static/tasks.jsx`

Capabilities:

- Task CRUD.
- Status and priority.
- Proposed commitments from extraction.
- Confirm/reject commitment flow.
- Confirmed commitments create/link tasks.
- Completing a task can mark commitment done.
- Chat can inject a small list of open commitments.

Limitations:

- No due dates.
- No scheduling.
- No subtasks.
- No task tags.
- Commitment extraction depends on model output.

## Scratchpad

Main files:

- `routers/scratchpad.py`
- `services/math_eval.py`
- `static/scratchpad.jsx`

Role:

- Lightweight expression/evaluation surface.
- Supports local deterministic math helpers.

Limitations:

- Not a full notebook.
- Not deeply audited in this pass.

## Flashcards

Main files:

- `services/flashcards.py`
- `routers/flashcards.py`
- `workers/cards.py`

Capabilities:

- Decks.
- Cards.
- Reviews.
- FSRS scheduling.
- Paste import.
- AI generation from source/note/research-like inputs.

Reality:

- Backend/API exists.
- No first-class frontend surface in current shell.
- Generation requires model config.
- FSRS compatibility not behaviorally audited in this pass.

## Email

Main files:

- `services/email.py`
- `workers/email.py`
- `routers/email.py`

Capabilities:

- Store IMAP/SMTP accounts with encrypted credentials.
- IMAP sync.
- Categorize with cheap model.
- Draft replies with active model.
- Send through explicit endpoint.
- Scheduled sync.

Reality:

- Backend exists.
- No first-class frontend email surface.
- No OAuth.
- Assumes app-password/basic credentials.
- No rich thread or attachment UI identified.

## MCP Tools

Main files:

- `services/mcp.py`
- `routers/mcp.py`

Capabilities:

- Configure MCP servers through app config.
- Spawn stdio JSON-RPC processes.
- List tools.
- Call tools.
- Approval gate based on `readOnlyHint`.
- Log calls.

Reality:

- Backend exists.
- No visible frontend management UI.
- Not integrated into chat as an autonomous tool loop.
- Configuring MCP servers is powerful because it can spawn local commands.

## Files And Public Shares

Main files:

- `services/files.py`
- `routers/files.py`

Capabilities:

- Upload/list/delete files.
- Download files.
- Public share links with expiry/max-download/rate behavior.
- Supported uploads can trigger document ingestion.

Reality:

- Backend exists.
- Documents and Projects use upload indirectly.
- Main shell still has Files nav with no surface.

## Skills

Main files:

- `services/skills.py`
- `routers/skills.py`

Capabilities:

- Store skills.
- Enable/disable skills.
- Inject enabled skill content into chat context.

Limitations:

- This is context injection, not a plugin/tool runtime.
- Skill safety depends entirely on content user adds.

## Jobs And Metrics

Main files:

- `workers/jobs.py`
- `services/metrics.py`
- `routers/metrics.py`

Job system:

- Jobs stored in SQLite.
- Atomic claiming.
- Worker loop with retry.
- Running jobs requeued on startup.
- Scheduled jobs registered at app startup.

Scheduled systems:

- Memory extraction/consolidation/pruning/calibration.
- Email polling.
- Memory inference.
- Prescient memory.
- Memory clustering.
- Weekly diff.

Limitations:

- Some jobs gracefully no-op without model config.
- Some progress systems are in-memory only.
- Job observability in UI is limited.

## Security And Deployment Reality

Atelier is local-first.

Reasonable assumptions:

- Single trusted user.
- Runs on localhost.
- Local disk is trusted.
- Model/search providers may be local or remote.

Risks if exposed publicly:

- Optional auth is not sufficient for hostile internet deployment.
- MCP configuration can spawn local commands.
- Public file shares intentionally bypass API auth.
- External frontend CDNs are used.
- Encrypted credentials are decryptable by the running app.
- No multi-tenant isolation.

## Current Known Bugs And Mismatches

1. Files nav is a placeholder.
   - `static/shell.jsx` includes `files`.
   - `static/app.jsx` has no `case 'files'`.
   - File/share backend exists, but no file manager UI.

2. Notes create contract mismatch.
   - Backend returns `{ok, note}`.
   - Frontend treats response JSON as the note itself.

3. Notes pin endpoint missing.
   - Frontend calls `/api/notes/{id}/pin`.
   - Router has no such route.

4. Flashcards/email/MCP are backend-only from the user's point of view.

5. Project delete semantics vs UI copy.
   - Backend disassociates docs/sessions/memory.
   - Some UI language suggests deletion/removal.

6. Project manifest query ranking is stubbed.
   - Branch exists for abstract ranking, but scores default to `0.0`.

7. Document/file lifecycle cleanup needs tests.
   - File bytes/rows and document rows/chunks are separate layers.

8. Some card-only chat answers may not persist as assistant messages.

9. Research memory promotion is not clearly implemented.
   - Treat docs/comments claiming automatic promotion as stale unless verified.

10. `llm.cheap()` fallback remains a cost-control trap.
    - New clustering/inference paths use `cheap_strict()`.
    - Older background paths can still silently use active model.

11. Real embedding validation is pending.
    - Clustering merge threshold and retrieval quality need a configured semantic
      embedding model and benchmark.

12. Full live regression status is unknown.
    - Only compile and non-invasive/temp-DB tests were run.

## Product Principles To Preserve

For future feature ideas, prefer designs that keep these properties:

- Local-first and single-user by default.
- Memory uncertainty is visible, not hidden.
- Proposed inferences are review-gated before retrieval.
- Background jobs handle slow/model-heavy work.
- Chat hot path stays bounded.
- Retrieval behavior remains inspectable.
- Live database is not abused by tests.
- New UI surfaces should be real workflows, not more placeholder nav.

## Best Feature Directions For GPT-5.5 To Explore

These are high-leverage because they build on the current architecture instead
of fighting it.

### 1. Memory Garden Rebuild

The backend now supports emergent strands and honest Unsorted state. The UI can
become a real "memory garden":

- Strand cards with counts, confidence distribution, newest/oldest atoms.
- Unsorted as a triage pool, not a shame bucket.
- Review queue integrated into strands.
- Strand detail page with timeline, provenance, proposed insights, and controls.
- "Why is this here?" explanation using nearest neighbors/centroid samples.
- Manual actions: rename strand, pin strand, split candidates, mark atoms
  unsorted, promote/demote salience.

Watchouts:

- Do not reintroduce static taxonomy.
- Do not create multi-membership until a real user pain proves it.
- Keep `NULL strand_id` meaningful.

### 2. Files Surface

There is backend functionality but no UI. A file manager would immediately make
the shell more honest:

- File list, upload, download, delete.
- Share link creation/revoke.
- Link expiry/max-download display.
- Relationship between file row and document ingestion status.
- "Promote to document" or "re-ingest" controls if supported.

Watchouts:

- Clarify file vs document lifecycle.
- Add cleanup tests before bulk delete controls.

### 3. Notes Contract Fix Plus Memory-Aware Notes

First fix the obvious bugs:

- Frontend create should use `data.note`.
- Add `/api/notes/{id}/pin` or remove pin UI.

Then explore:

- Optional note-to-memory promotion flow.
- Note backlinks to memories/research/docs.
- Co-writer provenance chips.
- Note collections attached to projects.

Watchouts:

- Docs say note ingestion was removed. Do not silently re-add automatic memory
  ingestion without an explicit user-controlled flow.

### 4. Search And Tool Invocation UX

Chat search is currently toggle-plus-intent. Ideas:

- Explicit "search web" command affordance.
- Search transparency panel: query, provider, freshness, sources.
- "Use current web?" suggestion cards that can be clicked.
- Provider health and quota view in Settings.

Watchouts:

- Do not make chat browse silently.
- Cite source provenance carefully.

### 5. Model And Embedding Setup Quality

The app quietly falls back to weak local hash embeddings. Better UX would help:

- Setup warning when `embedding_model` is unset.
- Embedding health panel with test queries.
- Recommended local embedding endpoint setup.
- Re-embed/recluster controls after embedding model changes.
- Cost-ceiling panel showing which background jobs can hit active model.

Watchouts:

- Re-embedding can be expensive and should be explicit.

### 6. Project Workspace Maturity

Projects already have scoped chat, docs, memory, instructions, and whole-file
loading. Next good ideas:

- Project dashboard: conversations, docs, open tasks, project memories.
- Safer project deletion/disassociation wording.
- True unassign vs delete for project documents.
- Project-specific strand view.
- Better manifest ranking with real abstract embeddings.

### 7. Research To Workspace Flow

Research has depth, sources, claims, entities, and reports. Missing product flow:

- Save claims to notes.
- Promote selected claims to memory with review.
- Turn research report into project document.
- Claim contradiction review.
- Source quality scoring.

Watchouts:

- Do not auto-promote research claims to memory without review.

### 8. Jobs And Background Activity UI

The backend has a job table but little user-facing observability:

- Settings panel for queued/running/failed jobs.
- Retry/cancel controls.
- Scheduled job last-run/next-run status.
- Memory clustering "run now" button.
- Document ingestion progress in one place.

### 9. Flashcards As A Real Surface

Backend is available. A first UI could include:

- Deck list.
- Due cards.
- Review loop.
- Import pasted content.
- Generate cards from note/research/document with preview before insert.

Watchouts:

- Keep review loop local and fast.
- Generation should be preview-gated.

### 10. Email As Optional Workbench

Backend exists but product surface is absent:

- Account setup.
- Inbox list.
- AI categories.
- Draft reply review.
- Explicit send button.

Watchouts:

- Security and credential UX need care.
- No OAuth currently.

## Engineering Priorities Before Big New Features

1. Add frontend smoke tests.
   - The frontend is buildless, so browser-level checks are valuable.

2. Add API contract tests for every frontend call.
   - Notes create/pin would have been caught immediately.

3. Separate test DB discipline everywhere.
   - New clustering/intake tests do this correctly.
   - Older tests still touch live DB.

4. Add file/document cleanup tests.

5. Add job observability.

6. Audit all `llm.cheap()` uses.
   - Decide where fallback to active is intended and where `cheap_strict()` is
     required.

7. Validate real embeddings.
   - Retrieval quality, clustering, and label merge thresholds all depend on
     semantic embeddings.

8. Run `scripts/bench.py` in a configured environment.
   - The retrieval-p95 invariant is likely fine because recent work is
     background-only, but it is not measured here.

## Practical Advice For GPT-5.5

When brainstorming:

- Treat Atelier as an active local prototype with serious backend depth.
- Prefer features that make existing systems visible and controllable.
- Do not propose generic SaaS/admin/multi-user features unless the product
  direction changes.
- Focus on the loop: chat -> memory/doc/project/research context -> review ->
  durable workspace artifact.
- Strong ideas should reduce cognitive burden, not add more surfaces to tend.

When implementing:

- Read the local code before trusting docs.
- Use `rg` first.
- Keep edits scoped.
- Avoid live DB mutation in tests.
- Preserve background-job boundaries.
- Be explicit about model tier and cost behavior.
- For memory, respect the Visibility Law: derived inferences are proposed until
  the user confirms them.

## Short Version

Atelier is a local FastAPI + SQLite + React AI workspace with a real chat,
retrieval, memory, project, document, and research backbone. The newest memory
work replaces static strands with emergent clustering and reduces review burden
through auto-reviewed stated facts, inference throttling, and soft retirement of
stale unreviewed facts. The biggest opportunities are making memory strands
usable in the UI, building the missing Files surface, fixing Notes contracts,
improving model/embedding setup, maturing Projects and Research workflows, and
adding job/background observability. The biggest risks are weak fallback
embeddings, stale docs, backend-only features, frontend/API mismatches,
`llm.cheap()` falling back to active model, and live-DB tests.
