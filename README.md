# Atelier

A self-hosted AI workspace with the hi-fi Atelier design.

## Quick start

```powershell
cd C:\Atelier
pip install -r requirements.txt
.\start.ps1
```

Then open **http://127.0.0.1:8000** in your browser.

## First run — connect a model

Type `/setup` in the chat composer to launch the setup wizard. Choose:

- **Local model server** — enter your endpoint URL (TabbyAPI, Ollama, llama.cpp, LM Studio)
- **Cloud API** — choose a provider and paste your API key

The wizard probes the endpoint, discovers available models, and lets you pick a default.

## Switching endpoints / models

- Click the amber **◆ model-name** chip in the composer to search and switch models
- Type `/setup` again at any time to add a new endpoint

## Keyboard

| Key | Action |
|-----|--------|
| `Enter` | Send message |
| `Shift+Enter` | New line |

## Configuration

Config (endpoints, active model, settings) is stored in `data/atelier.db` and managed via the UI. API keys are encrypted at rest. No manual editing needed. On first run, any legacy `data/*.json` files are imported into the database automatically.

Optional environment variables:

| Var | Purpose |
|-----|---------|
| `ATELIER_SECRET` | Passphrase used to derive the encryption key (portable across machines) |
| `ATELIER_AUTH=1` | Turn on shared-secret auth (default off on localhost) |
| `ATELIER_ORIGINS` | Comma-separated allowed CORS origins |
| `SEARXNG_INSTANCE` | Local SearXNG base URL for research/web search |

## Tech

- **Backend:** FastAPI + httpx, structured into `services/` (logic), `workers/` (background jobs), `routers/` (thin HTTP).
- **Storage:** SQLite (WAL, single serialized writer) with `sqlite-vec` for vectors and FTS5 for keyword search — one shared store behind a hybrid `retrieve()`.
- **Embeddings:** local-first (hashing fallback or a configured `/embeddings` endpoint), cached by content hash.
- **Scheduling:** APScheduler for periodic jobs; FSRS-6 (`fsrs`) for flashcards.
- **Frontend:** React 18 (CDN) + Babel in-browser, design system from Atelier hi-fi.

See [`docs/`](docs/index.md) for the full architecture and design rationale.
