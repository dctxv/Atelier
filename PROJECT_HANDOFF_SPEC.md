# Atelier Project Handoff Spec

Generated on 2026-06-23 from the current `C:\Atelier` checkout.

This report is meant for another AI or developer who needs an honest understanding of the current project. It is based on direct code inspection plus a small amount of verification. It does not assume the README or build summary are fully current.

## Verification Performed

Commands that passed:

```powershell
python -m compileall app.py services routers workers scripts
python -m scripts.test_intent
python -m scripts.test_retrieval_modes
```

Commands deliberately not run:

```powershell
python -m scripts.run_tests
```

Reason: the full runner starts its own server, uploads fixture documents, and can seed tens of thousands of memory atoms into the live SQLite database. That is too invasive for a read-only handoff report without explicit approval.

## Executive Summary

Atelier is a local-first AI workspace. It is a FastAPI backend with a SQLite core and a React 18 frontend served directly from `static/`. It is not a SaaS-style multi-user product. The current product is best understood as a single-user local AI cockpit with chat, memory, document retrieval, projects, research, notes, tasks, and several partially implemented or backend-only systems.

The strongest implemented areas are:

- Chat streaming against an OpenAI-compatible endpoint.
- SQLite-backed sessions and messages.
- Hybrid retrieval over memories and ingested document chunks.
- A structured memory system with extraction, reconciliation, review queues, questions, events, and inference workers.
- Document ingestion for text-layer PDF, DOCX, TXT, and Markdown.
- Project-scoped chats, instructions, documents, and memory.
- A deep research workflow with web search, chunking, synthesis, claim verification, and progress events.

The weaker or incomplete areas are:

- Several advertised surfaces are backend-only or have no real frontend.
- Some docs are stale or overstate what the current implementation does.
- Some frontend/backend API contracts are mismatched.
- Search, research, document abstracts, memory extraction, email classification, and co-writing all depend heavily on configured local or remote model endpoints.
- The fallback local embedding model is deterministic and offline, but semantically weak compared with real embeddings.
- The app is local-first and should not be treated as production-hardened for public exposure.

## Runtime And Startup

Main entry point: `app.py`.

Startup behavior:

- Creates a shared `httpx.AsyncClient`.
- Initializes SQLite through `services/db.py`.
- Runs legacy import/migration via `services/importer.py`.
- Starts KNN cache warming for memory retrieval.
- Registers scheduled background jobs.
- Starts the job worker system.
- Bootstraps memory strands.
- Mounts FastAPI routers.
- Serves the frontend from `/static`.

Routers included from `app.py`:

- Auth/config/chat/memory/notes/tasks/files/documents/projects/research/sessions/skills/flashcards/cowriter/email/MCP/search/web/metrics/scratchpad.

Auth:

- Authentication is optional.
- By default on localhost, auth is not required.
- `ATELIER_AUTH=1` enables shared-secret style auth.
- `/share/{token}` public file shares bypass normal auth by design.

CORS:

- Defaults to localhost origins.
- This is appropriate for local use, not enough by itself for a public deployment.

## Tech Stack

Backend:

- Python FastAPI.
- Uvicorn.
- SQLite with WAL mode.
- `sqlite-vec` for vector search.
- FTS5 for full-text search.
- `httpx` for LLM/search/provider calls.
- APScheduler for periodic jobs.
- `cryptography`/Fernet for local encrypted secrets.

Frontend:

- React 18 and ReactDOM loaded from local static files.
- Babel standalone is used in-browser.
- JSX files are fetched, transpiled in the browser, and evaluated.
- There is no Vite/Webpack/build step.
- External CDNs are used for KaTeX, Cytoscape, and Mermaid.

Important implication:

- The frontend is easy to hack on, but the browser runtime is fragile compared with a compiled app. Syntax or dependency issues can surface at runtime rather than build time.

## Repository Shape

Important top-level paths:

- `app.py`: FastAPI application entry point.
- `services/`: most persistent state, repositories, and core logic.
- `routers/`: HTTP API layers.
- `workers/`: background jobs and scheduled processing.
- `static/`: React UI, CSS, and browser assets.
- `docs/`: design notes and feature docs.
- `scripts/`: tests, benches, seed utilities, and helper scripts.
- `data/`: live SQLite database, uploads, and local runtime state.

The live SQLite database is expected at:

- `data/atelier.db`

Uploaded files are stored under:

- `data/uploads`

## Database And Core Storage

Schema source:

- `services/schema.sql`

Runtime migrations:

- Also exist in `services/db.py`.
- The schema is idempotent and continues evolving at startup.

Database implementation:

- WAL mode.
- Single writer queue/thread.
- Multiple reader workers.
- `sqlite-vec` extension loaded per connection.
- Embedding dimension is currently `256`.

Major table groups:

- Endpoint/config: model endpoints, settings, encrypted secrets.
- Chat: sessions, messages.
- Memory: atoms, vectors, FTS, events, questions, patterns, surfacing, review.
- Research: reports, chunks, sources, claims, entities, relations.
- Documents: files, documents, chunks, FTS, vector rows.
- Notes/tasks/commitments.
- Skills and flashcards.
- Email accounts/messages.
- MCP server logs.
- Search cache/provider usage.
- Jobs and metrics.
- Projects.

## Model And Embedding Behavior

The app assumes OpenAI-compatible APIs for chat and embeddings.

Config stores:

- Endpoint base URL.
- API key, encrypted locally.
- Active model.
- Cheap model.
- Search/weather/stock provider keys.

Embeddings:

- Preferred path: configured OpenAI-compatible `/embeddings` endpoint.
- Fallback path: deterministic local hash embedding, `local-hash-v1`.

Important limitation:

- The local hash embedding is fast and offline but not genuinely semantic. Retrieval will work better with a real embedding model.

Usage/cost telemetry:

- Usage is recorded when provider responses include token usage.
- Cost estimates depend on model registry pricing.
- If pricing is absent, estimated cost can be zero even when work happened.

## Frontend Navigation And Real Surfaces

Main frontend files:

- `static/index.html`
- `static/app.jsx`
- `static/shell.jsx`

Visible shell navigation includes:

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

Actual implemented frontend surfaces:

- Chat
- Projects
- Research
- Memory
- Notes
- Scratchpad
- Tasks
- Documents
- Settings

Important mismatch:

- `Files` exists in the shell navigation but has no corresponding real surface in `static/app.jsx`. It opens the generic placeholder. File upload/share backend exists, but there is no dedicated file manager UI.

No visible dedicated frontend surface found for:

- Flashcards
- Email
- MCP tools

Those systems have backend APIs, but they are not first-class UI surfaces in the current app.

## Chat System

Main files:

- `routers/chat.py`
- `services/sessions.py`
- `services/retrieval.py`
- `services/intent.py`
- `services/local_tools.py`
- `static/chat.jsx`

Core chat capabilities:

- SSE streaming from `/api/chat/stream`.
- Requires a configured active endpoint/model for normal LLM replies.
- Persists sessions and messages in SQLite.
- Supports global chats and project-scoped chats.
- Supports one-time migration from old browser localStorage chat history.
- Injects workspace context from memory and documents when retrieval policy allows.
- Can include project instructions, project manifests, whole-file snippets, active commitments, and enabled skills.
- Can emit provenance chips for memory/docs/web/computed context.
- Supports debug trace events when enabled.

Local deterministic tools:

- Time/clock.
- Math/unit expressions.
- Date math.
- Timezone difference.
- Base conversion.
- Hashing.
- Base64/URL encode/decode.
- Color conversion.
- Tip/split calculator.
- Weather and stock cards if external keys/providers are configured.

Search behavior:

- Web search is only used when the user toggles it on and intent classification decides it is useful.
- If search is off but the question looks current, the server may emit a suggestion event, but it does not browse automatically.
- Query rewriting can use the cheap model for harder/current searches.

Known chat limitations:

- If no active model endpoint is configured, normal chat returns an error.
- Deterministic local cards can appear live in the UI without creating a normal assistant text message in the session. After reload, some card-only answers may not be recoverable as proper assistant messages.
- The app assumes OpenAI-compatible streaming semantics.
- Local intent classification is useful, but not a substitute for robust tool planning.

## Retrieval System

Main file:

- `services/retrieval.py`

Retrieval combines:

- Memory vector KNN.
- Memory FTS.
- Document vector KNN.
- Document FTS.
- Pinned memory atoms.
- Project-scoped memory/docs.

Fusion:

- Reciprocal rank fusion style scoring.
- Memory has recency/decay behavior.
- Documents have dominance caps so large docs do not fully crowd out memory.
- Retrieval mode is selected by `services.intent`.

Retrieval modes include:

- `tool`
- `no_context`
- `factual`
- `technical`
- `exploratory`
- `personal`

Important behavior:

- `tool` and `no_context` suppress ambient personal memory.
- `technical` suppresses personal-flavored memory by default.
- Pinned memory and project context are structurally protected from normal suppression policies.
- Project context can force retrieval even when a generic prompt might otherwise suppress it.

Verified:

- The pure `scripts.test_retrieval_modes` test passed with 28/28 classification cases.

Limitations:

- Quality depends strongly on embeddings.
- Local hash embeddings are not semantically strong.
- Retrieval policy is heuristic, not a learned planner.

## Memory System

Main files:

- `services/memory.py`
- `routers/memory.py`
- `workers/extraction.py`
- `workers/memory_inference.py`
- `workers/memory_prescient.py`
- `workers/weekly_diff.py`
- `static/memory.jsx`

What memory atoms contain:

- Text.
- Type/category.
- Subject/predicate/object fields.
- Polarity/intensity/modality/confidence.
- Status and provenance.
- Scope/project fields.
- Vector and FTS entries.

Implemented memory operations include:

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
- Strands/graph/story-style views.

Extraction:

- Runs after chat turns via background job.
- Uses cheap model when configured.
- Has a significance gate before calling the model.
- Produces structured facts where possible.
- Reconciles duplicates, corroborations, retractions, and some conflicts.
- Proposed commitments can be extracted from user text.

Memory tiers:

- The UI/docs describe Essential/Living/Prescient style tiers.
- Worker code can auto-enable a basic/default memory tier if none is configured.

Important limitations:

- Extraction quality depends on the cheap model.
- Proposed inferences are not automatically trusted into retrieval until confirmed.
- Prescient/hypothesis systems exist but are best treated as experimental.
- There are many memory endpoints/UI panels; not all were behaviorally tested in this pass.

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

Ingestion process:

- Upload stores file bytes under `data/uploads`.
- Supported document types enqueue a background `ingest_document` job.
- Extraction reads text.
- Chunks are about 1000 characters with 150 character overlap.
- Chunks get FTS and vector rows.
- Cheap model may generate an abstract.
- Status becomes `ready` or `failed`.

Hard limits/behavior:

- Maximum document size is around 25 MB.
- Scanned/image-only PDFs fail because there is no OCR.
- Abstract generation is best effort.

Documents UI:

- Uploads files.
- Shows processing status.
- Shows document usage/ready state.
- Polls while processing.

Known limitations/issues:

- No OCR.
- No document viewer.
- No advanced chunk management.
- No batch lifecycle controls.
- Deleting a document clears document chunks/index rows, but file bytes and file rows are a separate layer.
- Deleting a file may not fully clean up document/index linkage in all paths.
- `services/documents._shape` does not expose `project_id`, so global document UI has limited visibility into document scope.

## Projects

Main files:

- `services/projects.py`
- `routers/projects.py`
- `static/projects.jsx`

Capabilities:

- Create/list/update/delete projects.
- Project-scoped chat sessions.
- Project-specific instructions.
- Project document uploads.
- Assign/remove project documents.
- Project-scoped memory atoms.
- Promote project memory to global.
- Project manifest injection into chat.
- Small project whole-file context.
- Librarian selection for explicit whole-file requests.

Important behavior:

- Project instructions override global persona for that project chat.
- Project docs and memory are scoped to that project.
- Global chat excludes project-scoped docs/atoms.

Known limitations/issues:

- Manifest ranking has a branch for query-based abstract scoring, but the score is currently stubbed at `0.0`; it is not doing real abstract similarity there.
- Some project librarian thresholds appear hardcoded in chat rather than always reading config.
- Removing a project document deletes the document, not merely unassigns it.
- Deleting a project disassociates docs/sessions/memory by setting `project_id` to null. It does not truly delete all conversations and project memory even if UI copy implies removal.

## Deep Research

Main files:

- `workers/research.py`
- `routers/research.py`
- `static/research.jsx`

Workflow:

- User starts a research job with a query and depth preset.
- Worker retrieves personal/workspace context.
- Cheap model plans subquestions.
- Search providers gather pages.
- Pages are chunked, embedded, deduplicated, and ranked.
- Active model synthesizes report sections/claims.
- Cheap model performs NLI-style claim verification.
- Entities and relations are extracted.
- Results persist into research tables.
- Progress is streamed through SSE.

UI:

- Research launcher.
- Depth presets.
- Recent reports.
- Live progress.
- Report view.
- Claims/evidence view.
- Sources rail.
- Contradiction/verification-oriented views.

Limitations:

- Requires working search providers and model endpoints.
- Search quality depends heavily on Tavily/Brave/SearXNG/DuckDuckGo availability.
- DuckDuckGo fallback is brittle and can be rate-limited.
- Synthesis JSON can fail; fallback behavior may produce sparse reports.
- Progress state is in memory, so server restart can lose live progress even if partial DB rows remain.
- Claim verification is model-assisted heuristic verification, not ground truth.
- Some docs imply high-confidence research claims are pushed into memory. The inspected worker did not clearly implement automatic memory promotion, so treat that claim as stale or unverified.

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

- Provider ordering and configuration.
- Encrypted provider keys.
- Freshness classification.
- Recency-aware cache TTL.
- Search cache.
- Provider usage metrics.
- Page extraction/enrichment.
- Reranking and deduplication.

Limitations:

- Tavily/Brave need keys.
- SearXNG needs a configured local or remote instance.
- DuckDuckGo fallback is unofficial and brittle.
- The chat system will not use web unless the toggle is on and intent allows it.

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
- Selection-based co-writing actions such as continue/rewrite/tighten.
- Co-writer can stream model output and use workspace retrieval.

Known issues:

- Frontend note creation expects the backend to return the note object directly, but the backend returns `{ok: true, note: ...}`. This likely breaks immediate new-note opening/listing until reload.
- Frontend calls `POST /api/notes/{id}/pin`, but no matching route was found. Pinning likely fails.
- `workers/cowriter.py` contains note-ingestion job code, but docs say note ingestion was removed and no enqueue path was found. Saved notes should not be assumed to enter memory automatically.
- Co-writing requires an active model.

## Tasks And Commitments

Main files:

- `services/tasks.py`
- `routers/tasks.py`
- `services/commitments.py`
- `static/tasks.jsx`

Capabilities:

- Basic task CRUD.
- Status and priority.
- Proposed commitments from memory extraction.
- User can confirm or reject proposed commitments.
- Confirmed commitments become tasks.
- Completing a task can mark commitment done.
- Chat can inject a short list of open commitments.

Limitations:

- No due dates.
- No scheduling.
- No subtasks.
- No task tags.
- Commitment extraction depends on model quality.
- Chat only injects a small top set of commitments.

## Scratchpad

Main files:

- `routers/scratchpad.py`
- `services/math_eval.py`
- `static/scratchpad.jsx`

Current role:

- A lightweight calculation/evaluation surface.
- Supports expression-style evaluation and local deterministic math helpers.

Limitations:

- Not deeply audited in this pass.
- Should be treated as a utility, not a full notebook.

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
- Import/generation flows.
- AI generation from source/note/research-style inputs using the cheap model.

Current product reality:

- Backend/API exists.
- No dedicated frontend surface was found in the loaded app/nav.
- AI generation appears synchronous in the route even though worker code exists.

Limitations:

- Requires model config for generation.
- FSRS package compatibility was not behaviorally tested in this pass.
- Not currently a visible user-facing feature unless driven through API.

## Email

Main files:

- `services/email.py`
- `workers/email.py`
- `routers/email.py`

Capabilities:

- Store email accounts with encrypted credentials.
- IMAP sync.
- Categorize messages with cheap model.
- Draft replies with active model.
- Send via SMTP only through explicit send endpoint.
- Scheduled sync registered.

Current product reality:

- Backend/API exists.
- No dedicated frontend email surface was found.

Limitations:

- No OAuth.
- Assumes basic/app-password style credentials.
- Snippet/body handling appears limited.
- No rich thread UI.
- No attachment workflow identified.
- Email features should be considered backend plumbing rather than a polished product area.

## MCP Tools

Main files:

- `services/mcp.py`
- `routers/mcp.py`

Capabilities:

- Configure MCP servers through app config.
- Spawn stdio JSON-RPC operations.
- List tools.
- Call tools.
- Approval gate based on `readOnlyHint`.
- Log calls.

Current product reality:

- Backend/API exists.
- No clear frontend management UI was found.
- Not integrated into chat as an autonomous model tool loop.

Limitations:

- Resources/prompts are not treated as first-class chat context.
- Tool calls are explicit API operations, not agentic chat tool use.
- Configuring MCP servers is powerful because it can spawn commands.

## Files And Public Shares

Main files:

- `services/files.py`
- `routers/files.py`

Capabilities:

- Upload/list/delete files.
- Download files.
- Create/list/revoke public share links.
- Share links can have expiry/max-download/rate-limit behavior.
- Supported document uploads create document ingestion jobs.

Current product reality:

- Backend/API exists.
- No dedicated frontend file manager exists despite shell navigation containing `Files`.
- Documents and Projects surfaces use upload functionality indirectly.

Known issue:

- File rows/bytes and document rows/chunks are separate layers. Delete paths do not obviously guarantee perfectly symmetric cleanup in every direction.

## Skills

Main files:

- `services/skills.py`
- `routers/skills.py`

Capabilities:

- Store skills.
- Enable/disable skills.
- Inject enabled skill content into chat system context.

Limitations:

- This is context injection, not a full plugin/tool runtime.
- Skill quality and safety depend on the content users add.

## Metrics And Jobs

Main files:

- `workers/jobs.py`
- `services/metrics.py`
- `routers/metrics.py`

Job system:

- Stored in SQLite.
- Atomic job claiming.
- Worker loop with retries.
- Max attempts around 3.
- Running jobs can be requeued on startup.
- Scheduled jobs registered at app startup.

Scheduled jobs include:

- Memory extraction.
- Email polling.
- Memory inference.
- Prescient memory passes.
- Weekly diff.

Limitations:

- Some jobs are no-ops or fail gracefully without model config.
- In-memory progress systems, such as research progress, do not survive restart cleanly.

## Security And Deployment Reality

Atelier is local-first.

Reasonable assumptions:

- Single trusted user.
- Runs on localhost.
- Local disk is trusted.
- Models/search providers may be local or remote.

Risks if exposed publicly:

- Optional auth is not enough for hostile internet deployment without review.
- MCP server configuration can spawn local commands.
- File shares intentionally bypass normal auth.
- External CDNs are used by the frontend.
- API keys and email credentials are encrypted locally, but the running app can decrypt them.
- There is no evidence of multi-tenant isolation.

## Documentation Accuracy

Useful docs exist:

- `README.md`
- `docs/index.md`
- `BUILD_SUMMARY.md`
- feature docs under `docs/`

But some docs are optimistic or stale:

- `BUILD_SUMMARY.md` claims a previous all-tests-passing snapshot. That was not revalidated here.
- Notes docs say note ingestion was removed; code comments/job names still suggest note ingestion exists.
- Research docs/comments imply possible memory promotion of claims, but inspected worker code did not clearly show that implemented.
- UI copy around project deletion may imply deletion of conversations/project memory, while backend disassociates them.

## Known Bugs And Mismatches To Prioritize

1. Notes create response mismatch:
   - Backend returns `{ok, note}`.
   - Frontend appears to treat the whole response as a note.
   - Likely user-visible bug.

2. Notes pin endpoint missing:
   - Frontend calls `/api/notes/{id}/pin`.
   - No matching route found.
   - Pin toggle likely fails.

3. Files nav placeholder:
   - Shell advertises `Files`.
   - App has no real Files surface.

4. Flashcards/email/MCP are backend-only:
   - APIs exist.
   - No first-class UI surfaces found.

5. Project delete behavior vs UI copy:
   - Backend nulls project IDs on docs/sessions/memory.
   - It does not fully delete them.

6. Project manifest query ranking:
   - Abstract scoring branch appears stubbed at `0.0`.

7. Document/file cleanup asymmetry:
   - Document delete and file delete are separate.
   - Orphan risks should be tested.

8. Card-only chat answers:
   - Some deterministic cards may not persist as normal assistant messages.

9. Research claim memory promotion:
   - Docs/comments imply it.
   - Implementation was not found or not obvious.

10. Full regression status unknown:
   - Only compile and pure smoke tests were run.
   - Full server/model integration suite was intentionally not run.

## Practical Brainstorming Directions

High-impact product work:

- Fix the Notes API/UI mismatches.
- Build a real Files surface or remove the nav item.
- Decide whether Flashcards, Email, and MCP are real product surfaces or backend experiments.
- Add a document viewer and better document lifecycle controls.
- Make project delete semantics explicit and safe.
- Add OCR if scanned PDFs matter.
- Improve embeddings setup UX so users do not unknowingly rely on weak hash embeddings.

High-impact AI quality work:

- Add a robust tool loop for chat rather than only local heuristics plus search toggle.
- Make web search behavior more transparent and easier to invoke.
- Improve research verification and source quality controls.
- Add explicit memory promotion flows from research and notes if desired.
- Strengthen retrieval evaluation with repeatable non-invasive test fixtures.

High-impact engineering work:

- Add a real frontend build/test pipeline or at least automated browser smoke tests.
- Add API contract tests for every frontend route call.
- Separate test database from live `data/atelier.db`.
- Add cleanup/sweep tests for files/documents/project deletes.
- Make scheduled/background job observability more visible in Settings.

## Short Version For Another AI

Atelier is a local FastAPI + SQLite + React AI workspace. It has a real chat/memory/document/project/research backbone, but several advertised systems are partial. The best parts are hybrid retrieval, structured memory, document ingestion, project-scoped context, and research jobs. The weak spots are frontend/backend mismatches, backend-only feature areas, stale docs, model/provider dependency, no OCR, no real file manager, and local-first security assumptions. Treat it as an active prototype with substantial backend depth, not as a polished finished app.

