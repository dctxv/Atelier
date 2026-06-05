# The Atelier

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

Config is stored in `data/config.json` and managed via the UI. No manual editing needed.

## Tech

- **Backend:** FastAPI + httpx (streams SSE responses from any OpenAI-compatible endpoint)
- **Frontend:** React 18 (CDN) + Babel in-browser, design system from The Atelier hi-fi
