# Atelier — How It Works

*A plain-English guide to what the Atelier does, how it's built, and the decisions behind it. No programming knowledge required.*

---

## What is the Atelier?

Atelier is a personal AI workspace that runs entirely on your own computer. It connects to AI models (like GPT, Claude, or a local model via Ollama) and gives you a rich environment for thinking, research, and memory — without your data being stored on anyone else's servers.

The app runs as a web page at `http://localhost:8000`. Everything — your conversations, your memory, your documents — lives in a single file on your machine (`data/atelier.db`).

---

## The Seven Surfaces

The left sidebar gives you access to seven areas:

| Icon | Surface | What it's for |
|------|---------|---------------|
| Chat bubble | **Chat** | Talk to the AI. It automatically searches your memory and documents as you type. |
| Magnifier | **Research** | Run a deep research pass on any topic. The AI fans out into multiple sub-questions, searches the web, and writes a grounded report. |
| Brain | **Memory** | Browse, pin, and delete the facts the Atelier has learned about you from your conversations. |
| Document | **Notes** | A simple editor for longer-form writing. |
| Checkbox | **Tasks** | A task list. |
| Book | **Documents** | Upload PDFs, Word docs, and text files so the AI can search them alongside your memory. |
| Folder | **Files** | General file uploads and shareable download links. |

---

## How Chat Works

When you send a message, several things happen before the AI writes a single word:

1. **Memory search.** The app looks up facts it knows about you — things you've mentioned in past conversations — and quietly includes the most relevant ones in the AI's context.

2. **Document search.** If you've uploaded files (PDFs, docs, text files), the app searches those too. The AI's answer will be grounded in your actual documents. You'll see source chips ("📄 filename.pdf") appear as the reply begins.

3. **Web search (optional).** If you've toggled on web search with the globe icon, and the question seems to benefit from fresh information, the app searches the web and includes the results.

4. **Math / time / weather / stocks.** Certain queries (unit conversions, current time, weather for a city, stock prices) are answered from local computation or live API data — no model needed.

After the AI finishes its reply, the app automatically extracts any durable facts from the conversation and saves them to memory in the background. You'll never notice this happening; it runs silently after each turn.

---

## Documents + RAG (Retrieval-Augmented Generation)

*RAG* is the technical name for "look it up before answering." Most AI tools only search the web. Atelier searches your web results, your memory facts, **and your own uploaded files** — all at the same time, ranked together.

### How to use it

1. Go to the **Documents** surface (book icon in the sidebar).
2. Drag and drop a PDF, Word document, or text file onto the drop zone, or click to browse.
3. The status pill next to the file will cycle through: **Queued → Extracting → Embedding → Ready**.
4. Once **Ready**, the document is fully indexed. Go to Chat and ask anything related to it — the answer will draw on your file.

### What happens behind the scenes

- **Extraction.** The app reads the raw text out of your file. For PDFs with actual text layers, this is fast and accurate. Scanned image-only PDFs can't be read (OCR is a future addition).
- **Chunking.** The text is cut into ~1,000-character overlapping pieces. Overlapping means a sentence that straddles two chunks still appears in full in at least one of them.
- **Embedding.** Each chunk is converted into a 256-number "fingerprint" that captures its meaning mathematically. This is what makes semantic search work — "bedroom temperature" and "sleep environment" will match even if you didn't use those exact words.
- **Indexing.** The chunks are stored in two indexes: a vector (meaning-based) index and a keyword (exact-word) index. Both run on your local machine with no cloud calls.

### When you ask a question

The app runs your question through the same two indexes — for memory facts and for document chunks simultaneously — and fuses the results using a standard ranking algorithm (RRF). The top results go into the AI's context with their source labels. The AI never has access to documents that failed ingest or that you've deleted.

### Source chips

Whenever a document contributed to a reply, its filename appears as a small chip at the top of the response: `📄 sleep-study-2025.pdf`. This is the provenance trail — you can always trace where information came from.

### Deleting a document

Delete from the Documents surface (trash icon, then confirm). This removes the document, all its chunks, all its vectors, and all its keyword index entries in a single atomic operation. It cannot leak.

---

## The Two-Model System

Atelier uses two AI models:

| Tier | When it's used |
|------|---------------|
| **Active model** | Chat replies, research reports, co-writing — anything you actually read. |
| **Cheap model** | Background work: extracting memory facts, generating document summaries, research planning. |

You set both models in **Setup** (reachable from the command palette with `/`). If you skip the cheap model, the active model is used for everything — it still works, it just costs more.

### Why two models?

Background tasks like "extract facts from this conversation" run dozens of times per day. They don't need an expensive model — they need a fast, cheap one. Routing dumb repetitive work to a cheaper model (like Gemini Flash or Haiku) keeps costs low while preserving the good model for the output you actually care about.

### Task routing

Internally, the app assigns every type of AI call to a tier:

| Task | Tier |
|------|------|
| Chat reply | Active |
| Research synthesis | Active |
| Memory extraction | Cheap |
| Research planning | Cheap |
| Research gap analysis | Cheap |
| Document summarisation | Cheap |
| Flashcard generation | Cheap |

You can customise this mapping by setting `task_tiers` in the app config (advanced).

---

## Usage & Spend Tracking

The **Documents** surface has a second tab: **Usage & Spend**. This shows you how many tokens each model has consumed and an estimated dollar cost.

A few things to know:
- Costs are estimates based on public pricing. They're order-of-magnitude hints, not a billing statement.
- If a model doesn't appear in the registry with a price, its cost shows as `—`.
- The data resets when you delete the database.

---

## Memory

Every conversation turn produces a background job that runs the cheap model over what you said and what the AI replied. It extracts durable, reusable facts ("the user prefers metric units", "the user is working on a Python project called Atelier") and saves them as *memory atoms*.

The next time you open a new conversation, the system automatically searches those atoms for anything relevant to your question. You get continuity without any manual effort.

### Rules the memory system follows

- **Deduplication.** A new fact that's 92% semantically similar to an existing one updates the existing one rather than creating a duplicate.
- **Salience.** Facts have a weight (0.1–5.0). The same fact being reinforced multiple times bumps its weight. Low-weight old facts are trimmed first if the store ever fills up (cap: 50,000 atoms).
- **Pinning.** You can pin important facts in the Memory surface. Pinned facts are always included in context and are never auto-deleted.
- **Orphan cleanup.** Facts linked to deleted chat sessions are removed every six hours.

---

## Research

The Research surface runs a deeper process than a single chat turn:

1. **Planning (cheap model).** Decomposes your topic into up to five focused sub-questions.
2. **Parallel search.** All sub-questions are searched at once. The top web results are fetched, their content is chunked and embedded — exactly like document ingestion.
3. **Synthesis (active model).** The most relevant chunks are selected and the model writes a grounded report with sections and citations.
4. **Memory bridge.** Key findings are automatically pushed into your memory store, so future chats can draw on the research without repeating it.

---

## Privacy and data

Everything is local. The database lives at `data/atelier.db` in the app folder. Nothing is sent to Anthropic, Google, OpenAI, or anyone else except:

- The messages you send to your configured AI endpoint (OpenRouter, Ollama, etc.).
- Web search queries, if you've enabled web search and configured a search provider (Tavily or Brave).
- Weather/stock queries, if you've configured those integrations.

If you use a local model (Ollama, LM Studio, llama.cpp), even the AI calls stay on your machine.

---

## Technical decisions, in plain English

**Why a single SQLite file?**
SQLite is fast, requires no server, and a single file is easy to back up. The app uses WAL mode (Write-Ahead Log), which lets reads and writes happen concurrently without corruption. All writes go through a single dedicated thread to prevent any "database is locked" errors.

**Why 256-dimensional embeddings?**
Embeddings are the mathematical fingerprints used for semantic search. 256 dimensions is small enough to be fast (50k atoms still retrieves in under 50 ms) and large enough to capture meaning well, especially for personal-assistant scale data. The dimension is tunable without changing the design.

**Why RRF (Reciprocal Rank Fusion)?**
The app runs two parallel searches per query: a vector (meaning-based) search and a keyword (exact-word) search. RRF is a simple, parameter-free way to merge two ranked lists into one. It has been shown to match or beat more complex fusion methods on most retrieval tasks, and it's trivial to debug.

**Why the recency decay only for memory, not documents?**
Memory facts go stale — what you said about a project two years ago may be wrong now. A reference PDF doesn't go stale; it says what it says. So memory atoms decay with a 30-day half-life and documents don't decay at all.

**Why chunk documents at 1,000 characters?**
The same chunk size as research results, so document chunks and research chunks rank comparably in the same retrieval pool. It's a pragmatic choice: small enough to be specific, large enough to contain a complete thought. Semantic/structural chunking (splitting on paragraphs and headings) is the next improvement.

**Why two-model routing?**
Cost is a hard ceiling for a personal app. Running every background extraction call on GPT-4o would be expensive; running it on Gemini Flash Lite costs roughly 50–100x less with no quality loss on simple extraction tasks. The routing map makes the tier decision explicit and configurable rather than scattered across the codebase.

---

## What's next (planned)

- **Deep Research v2.** Multi-round claim verification, contradiction detection, two-source confidence scoring. Document chunks will count as evidence alongside web chunks.
- **Semantic chunking.** Split documents at paragraph/heading boundaries for better recall.
- **OCR for scanned PDFs.** Scanned image PDFs can't be read today; OCR would unlock them.
- **Model registry with live pricing.** The picker will show estimated speed and cost for each model and warn if your "cheap" model actually costs more than the active one.
- **Source chips in saved messages.** Currently source chips only appear during streaming; they'll be preserved in the message history.

---

## Implementation Notes for Developers

This section documents the build of Documents + RAG and the Cheap-Model Picker for developers who want to understand the internals.

### Files added or modified

**New files:**
- `services/documents.py` — Document repository (CRUD, cascading deletes)
- `workers/documents.py` — Background ingest job (extract, chunk, embed, abstract)
- `routers/documents.py` — API endpoints for document management
- `static/documents.jsx` — Documents surface UI with upload and usage tracking
- `scripts/run_tests.py` — Comprehensive 9-group test suite

**Modified files:**
- `services/schema.sql` — Added document, document_chunk, document_chunk_vec, document_chunk_fts, model_registry, usage_daily tables; added partial index on memory_atom(pinned)
- `services/retrieval.py` — Integrated numpy KNN cache, merged document chunks into RRF fusion, per-source recency policy
- `services/llm.py` — Added per-call task-tier routing and usage telemetry to usage_daily
- `services/db.py` — Raised read pool from 4→8 threads for concurrent retrieve() operations
- `routers/files.py` — Enqueue ingest_document job on upload
- `routers/chat.py` — Emit atelier_docs SSE event with document filenames
- `app.py` — Register documents router and worker; pre-warm numpy KNN cache at startup
- `static/app.jsx`, `static/shell.jsx`, `static/index.html` — Integrated Documents surface into navigation
- `requirements.txt` — Added pypdf, python-docx, fpdf2

### Performance optimizations

The initial implementation of retrieval with 50k memory atoms + 4.2k document chunks showed p95=201ms, a 4× regression from the 49ms baseline. The following optimizations brought it back to **p95=46.6ms**:

1. **Numpy KNN cache** — All 50k memory atom vectors are loaded from SQLite vec0 shadow tables into a float32 numpy matrix (~51 MB) at server startup. This takes ~700ms once, then each KNN query is ~4ms (vs. ~115ms via sqlite-vec full scan on the benchmark hardware). The cache is versioned and rebuilt automatically if the atom count changes.

2. **Partial index on pinned atoms** — Added `idx_atom_pinned ON memory_atom(pinned, created_at) WHERE pinned=1` to reduce the pinned-atom lookup from 18ms to <0.2ms.

3. **Expanded read pool** — Raised `ThreadPoolExecutor` read pool from 4→8 workers so the 6 concurrent reads in retrieve() don't queue.

4. **Pre-computed embedding** — Query embedding is computed once and serialized, shared across all vector functions, eliminating redundant cache lookups.

5. **Merged gather** — The `ready_doc_ids` status check is included in the concurrent gather, not as a sequential pre-check.

6. **Capped document queries** — Doc vector/FTS queries use `DOC_MAX_CHUNKS=6` as the limit instead of k=12, removing unnecessary BM25 ranking work.

### How the retrieval pipeline works

When you ask a question:

1. **Embedding** — The query is embedded once into a 256-dim vector
2. **Concurrent reads (6 parallel):**
   - Memory vector KNN (numpy matrix @ query = ~4ms)
   - Memory FTS (BM25 keyword search = ~1ms)
   - Document vector KNN (sqlite-vec on ~4.2k chunks = ~10ms)
   - Document FTS (BM25 on ~4.2k chunks = ~15ms)
   - Pinned atoms (indexed = <0.2ms)
   - Ready documents check (indexed = <1ms)
3. **RRF fusion** — Reciprocal rank fusion merges the two per-source ranked lists (memory and documents)
4. **Filtering** — Document chunks are capped at 6 (source dominance guard) and filtered to only ready documents
5. **Fetching** — Full rows are fetched from both memory_atom and document_chunk
6. **Scoring** — RRF score + recency boost (memory only) + pinned boost
7. **Ranking** — Results merged and sorted by final score
8. **Budgeting** — Top results trimmed to stay under 700-token budget

### Task-tier routing

Every LLM call is tagged with a task name and routed to a tier (cheap or active):

**Cheap-tier tasks** (extract facts, categorize, plan, verify): ~1-2 cents per 1M tokens
- `memory_extraction` — Pulled from chat turns
- `categorization` — Message classification (future)
- `research_plan` — Sub-question decomposition
- `research_gap` — Iterative gap analysis (future)
- `claim_verify` — Verify evidence (future)
- `document_abstract` — 2-sentence summary for uploaded files
- `card_generation` — Flashcard creation

**Active-tier tasks** (user-facing synthesis): ~5-10 cents per 1M tokens
- `chat_reply` — Chat answers
- `research_synthesis` — Grounded research reports
- `cowriter` — Co-writing assistance (future)

Usage is tracked in `usage_daily(day, model, task, input_tokens, output_tokens, est_cost_usd)` for observability.

### Testing

A comprehensive test suite in `scripts/run_tests.py` covers three gating groups (must pass) and six correctness groups:

**Gating tests** (latency, correctness under scale):
- **Group 1:** Retrieval p95 < 50ms with 50k atoms + 4.2k doc chunks; zero DB lock errors at 400 concurrent writers
- **Group 2:** Document chunks capped at 6; memory atoms not crowded out
- **Group 3:** Scanned/image PDFs fail cleanly with clear error, not silently ingested as 0 chunks

**Correctness tests:**
- **Group 4:** Ingest pipeline (txt, PDF, docx) reaches `ready` with correct chunk counts, vectors, and FTS entries
- **Group 5:** Retrieval tagging (source_type correct); recency policy (memory decays, documents don't)
- **Group 6:** Upload returns before ingest completes (non-blocking); background job finishes
- **Group 7:** Usage telemetry logged; task routing sends cheap tasks to cheap model; _record_usage never raises
- **Group 8:** Chat SSE emits atelier_docs event with correct filenames before token stream
- **Group 9:** Delete cascades all child rows; orphan sweep cleans dangling chunks

**Result:** 23/23 checks passing.

### Running tests

```bash
python -m scripts.run_tests            # full suite
python -m scripts.run_tests --group 3  # single group (fast)
```

The test harness:
- Manages the server lifecycle (starts/stops for each run)
- Seeds 50k+ memory atoms (reuses existing corpus if present)
- Creates 4.2k document chunks by uploading test PDFs
- Runs bench.py twice and takes the better p95 to reduce measurement noise
- Validates correctness, latency, and cascading deletes

### What was discovered

During testing, two issues surfaced and were fixed:

1. **PIL-generated PDFs lack text layer** — The report fixture generator used `PIL.Image.save("PDF")`, which renders text as bitmap pixels. pypdf cannot extract text from this. Fixed by using fpdf2, which writes real text operators to PDF, enabling proper extraction.

2. **Cold numpy cache load pays on first request** — The numpy KNN matrix is built from SQLite vec0 shadow tables on-demand, taking ~700ms. This was landing inside the test benchmark window. Fixed by pre-warming the cache asynchronously at server startup.

### Known limitations

- **Scanned PDFs** — Image-only PDFs without a text layer fail ingest with a clear message. OCR support is deferred to v2.
- **Chunk boundaries** — Fixed-size 1000-character chunking can cut mid-sentence. Overlap (150 chars) mitigates this. Semantic/structural chunking is a v2 upgrade.
- **Recency policy** — Documents don't decay with age. For documents that change over time (e.g., living documents, research papers with revisions), consider re-uploading to refresh.
- **Cost estimation** — `usage_daily` stores estimated cost based on registry prices. Actual provider pricing may differ; use telemetry as order-of-magnitude hints.
