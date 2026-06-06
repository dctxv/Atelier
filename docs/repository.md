# Repository & Infrastructure

*Git setup, secrets, start script, and how to run the app.*

---

## Running the app

```
cd c:\Atelier
.\start.ps1
```

That's it. The start script kills anything already running on port 8000 (so you don't get "address already in use" errors), prints the URL, and starts the server. Open `http://127.0.0.1:8000` in a browser.

The server uses `--reload` so changes to `app.py` restart it automatically. Frontend changes (JSX, CSS) are served as static files — you just hard-refresh the browser (`Ctrl+Shift+R`) after editing them. Bump the `?v=YYYYMMDD` version string in `index.html` to bust the browser cache when changing a component file.

---

## What start.ps1 does

```powershell
Set-Location $PSScriptRoot

$conn = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($conn) {
    Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
}

Write-Host "  The Atelier v2  http://127.0.0.1:8000" -ForegroundColor DarkYellow

python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

The port-kill step matters because during development it's easy to have a stale uvicorn process sitting on port 8000 from a previous session (e.g. if you closed the terminal without stopping the server). Without the kill step, the new start fails immediately.

---

## Git and secrets

### The incident

The `data/config.json` file — which contains API endpoint URLs and API keys — was included in the initial commit. This wasn't caught before the first commit because there was no `.gitignore` yet.

The repo had a GitHub remote configured. The commit had not been pushed yet when this was caught, so no keys were ever public. But the keys existed in the local git object store.

**Both OpenRouter keys in that config should be treated as compromised and rotated**, even though they were never pushed. The local git object store can be scanned by other tools, and there's no guarantee the objects weren't backed up or synced elsewhere.

### What was done

1. Created `.gitignore` — covers the entire `data/` directory, `__pycache__/`, log files, `.env`, virtualenv directories
2. Removed all `data/*.json` files from git tracking with `git rm --cached`
3. Created `data/config.example.json` — a template showing the expected config structure with placeholder values
4. Amended the initial commit so the API keys were never in any commit object

The amendment was safe because:
- There was only one commit in the repo
- It had not been pushed to the remote

After the amend, the git history has zero trace of the keys.

### What the .gitignore covers

```
data/              ← all user data — config, memory, notes, sessions
!data/config.example.json    ← except the template (force-added)
__pycache__/
*.py[cod]          ← compiled Python
*.pyo
.env
.venv/ venv/       ← virtual environments
server.log
server.err
*.log
.DS_Store
Thumbs.db
```

The `!data/config.example.json` negation doesn't work automatically with git's directory-level ignore — git can't un-ignore files inside an ignored directory without a force-add. The example file was force-added with `git add -f`. Future changes to the example file will also need `git add -f data/config.example.json`.

### data/ — user data that never belongs in git

Everything in `data/` is personal runtime state. None of it belongs in version control:

| Path | Contents |
|---|---|
| `atelier.db` (+ `-wal`, `-shm`) | The SQLite database — config, memory, notes, research, cards, mail, jobs, everything. API keys are stored **encrypted** here. |
| `.fernet.key` | The encryption key used when no `ATELIER_SECRET` passphrase is set. Losing it means the encrypted endpoint keys can't be decrypted. |
| `uploads/` | Uploaded file blobs (referenced by the `file` table). |
| `config.json`, `memory.json`, `notes.json`, … | The legacy JSON files. Retired after the one-time import, kept on disk as a safety net. No longer read by the app. |

Even the files that don't contain secrets don't belong in git. They're personal data that changes constantly. There's no reason for version control to track them. The existing `data/` rule in `.gitignore` already covers all of the above, including the new `atelier.db` and `.fernet.key`.

> The old worry from "the incident" (API keys sitting in plaintext `config.json`) is now structurally fixed: keys live encrypted in the DB, are decrypted only in-process to build request headers, and are never returned by any endpoint. See [shared-core.md](shared-core.md#6-access--secrets).

---

## Deploying or moving machines

If you want to move the Atelier to a new machine or share a clean copy:

1. Clone the repo (no `data/` files will be included)
2. Create `data/config.json` from `data/config.example.json`
3. Fill in your real endpoint URL and API key
4. Run `pip install -r requirements.txt`
5. Run `.\start.ps1`

The frontend requires no install step. The libs are in `static/lib/`.

---

## Why there's no docker, no requirements lock, no CI

This is a personal local tool. Docker would add complexity with zero benefit for a single-user local app. A locked requirements file (`requirements.txt` is already minimal — FastAPI, uvicorn, a few others) would be useful if there were a deployment target. CI would be useful if there were a test suite or multiple contributors. None of those apply yet.

If The Atelier ever becomes something that other people run, the right additions in order would be: a locked requirements file, a Dockerfile, and eventually tests for the backend API. The frontend's "tests" are just opening the browser and seeing if it works.
