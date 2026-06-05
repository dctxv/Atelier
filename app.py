"""The Atelier — FastAPI backend."""
from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio, httpx, json, uuid, os, re, mimetypes
from html import unescape
from urllib.parse import quote_plus
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

app = FastAPI(title="The Atelier")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR   = Path("data")
UPLOADS_DIR = DATA_DIR / "uploads"

CONFIG_FILE   = DATA_DIR / "config.json"
MEMORY_FILE   = DATA_DIR / "memory.json"
NOTES_FILE    = DATA_DIR / "notes.json"
TASKS_FILE    = DATA_DIR / "tasks.json"
FILES_FILE    = DATA_DIR / "files.json"
RESEARCH_FILE = DATA_DIR / "research.json"
SKILLS_FILE   = DATA_DIR / "skills.json"

DEFAULT_CONFIG = {
    "endpoints": [],
    "active_endpoint_id": None,
    "active_model": None,
}


# ── Storage helpers ──────────────────────────────────────────────────────────

def _ensure():
    DATA_DIR.mkdir(exist_ok=True)
    UPLOADS_DIR.mkdir(exist_ok=True)
    if not CONFIG_FILE.exists():
        _write_cfg(DEFAULT_CONFIG.copy())


def _read_cfg() -> dict:
    _ensure()
    with open(CONFIG_FILE) as f:
        return json.load(f)

# Keep original name as alias used throughout
def _read() -> dict:
    return _read_cfg()


def _write_cfg(cfg: dict):
    _ensure()
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

def _write(cfg: dict):
    _write_cfg(cfg)


def _read_json(path: Path, default=None):
    if default is None:
        default = []
    _ensure()
    if not path.exists():
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path: Path, data):
    _ensure()
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _active_ep(cfg: dict) -> dict | None:
    eid = cfg.get("active_endpoint_id")
    for ep in cfg.get("endpoints", []):
        if ep["id"] == eid:
            return ep
    return None


def _normalize(url: str) -> str:
    url = url.rstrip("/")
    if not url.endswith("/v1"):
        url += "/v1"
    return url


def _headers(ep: dict) -> dict:
    h = {"Content-Type": "application/json"}
    if ep.get("api_key"):
        h["Authorization"] = f"Bearer {ep['api_key']}"
    return h


def _time_fallback_results(query: str) -> list[dict]:
    q = (query or "").lower()
    if not any(k in q for k in ("time", "date", "clock")):
        return []
    zone_map = {
        "sydney": "Australia/Sydney", "melbourne": "Australia/Melbourne",
        "brisbane": "Australia/Brisbane", "perth": "Australia/Perth",
        "adelaide": "Australia/Adelaide", "auckland": "Pacific/Auckland",
        "tokyo": "Asia/Tokyo", "london": "Europe/London",
        "new york": "America/New_York", "los angeles": "America/Los_Angeles",
        "utc": "UTC",
    }
    selected_zone = "UTC"
    for key, zone in zone_map.items():
        if key in q:
            selected_zone = zone
            break
    try:
        z = ZoneInfo(selected_zone)
    except Exception:
        z = timezone.utc
        selected_zone = "UTC"
    now = datetime.now(z)
    local_now = datetime.now().astimezone()
    return [{
        "title": f"System time ({selected_zone})",
        "url": "local://system-clock",
        "content": (
            f"{now.strftime('%A, %d %B %Y %H:%M:%S %Z')} "
            f"(ISO: {now.isoformat()}). "
            f"Host local time: {local_now.strftime('%Y-%m-%d %H:%M:%S %Z')}."
        ),
    }]


# ── Web search ────────────────────────────────────────────────────────────────

@app.post("/api/web-search")
async def web_search(request: Request):
    data = await request.json()
    query = (data.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "Missing query", "results": []}

    searxng = os.getenv("SEARXNG_INSTANCE", "http://localhost:8080").rstrip("/")

    def _clean_html(text: str) -> str:
        text = re.sub(r"<[^>]+>", " ", text or "")
        text = unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(f"{searxng}/search", params={"q": query, "format": "json", "language": "en", "safesearch": 0})
            resp.raise_for_status()
            raw_results = resp.json().get("results", [])[:6]
        results = [{"title": (r.get("title") or "").strip(), "url": (r.get("url") or "").strip(), "content": (r.get("content") or "").strip()} for r in raw_results if r.get("url")]
        if results:
            return {"ok": True, "provider": "searxng", "results": results}
    except Exception:
        pass

    try:
        ddg_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
        ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            resp = await client.get(ddg_url, headers=ua)
            resp.raise_for_status()
            html = resp.text
        blocks = re.findall(r'<div class="result__body">(.*?)</div>\s*</div>', html, flags=re.DOTALL | re.IGNORECASE)[:8]
        results = []
        for block in blocks:
            lm = re.search(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, flags=re.DOTALL | re.IGNORECASE)
            if not lm:
                continue
            url = unescape(lm.group(1)).strip()
            title = _clean_html(lm.group(2))
            sm = re.search(r'class="result__snippet"[^>]*>(.*?)</(?:a|div)>', block, flags=re.DOTALL | re.IGNORECASE)
            content = _clean_html(sm.group(1) if sm else "")
            if url and title:
                results.append({"title": title, "url": url, "content": content})
            if len(results) >= 6:
                break
        if results:
            return {"ok": True, "provider": "duckduckgo", "results": results}
    except Exception:
        pass

    time_results = _time_fallback_results(query)
    if time_results:
        return {"ok": True, "provider": "local-time", "results": time_results}

    return {"ok": False, "error": "No web results found. SearXNG is unreachable and outbound fallback search could not connect.", "results": []}


# ── Config ───────────────────────────────────────────────────────────────────

@app.get("/api/config")
async def get_config():
    cfg = _read()
    return {"endpoints": cfg.get("endpoints", []), "active_endpoint_id": cfg.get("active_endpoint_id"), "active_model": cfg.get("active_model")}


@app.patch("/api/config")
async def patch_config(request: Request):
    data = await request.json()
    cfg = _read()
    for key in ("active_endpoint_id", "active_model"):
        if key in data:
            cfg[key] = data[key]
    _write(cfg)
    return {"ok": True}


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/api/endpoints")
async def list_endpoints():
    return {"endpoints": _read().get("endpoints", [])}


@app.post("/api/endpoints")
async def add_endpoint(request: Request):
    data = await request.json()
    cfg = _read()
    ep = {"id": str(uuid.uuid4()), "name": data.get("name", "Unnamed"), "url": _normalize(data["url"]), "api_key": data.get("api_key", ""), "type": data.get("type", "local")}
    cfg.setdefault("endpoints", []).append(ep)
    if not cfg.get("active_endpoint_id"):
        cfg["active_endpoint_id"] = ep["id"]
    _write(cfg)
    return {"endpoint": ep}


@app.delete("/api/endpoints/{endpoint_id}")
async def delete_endpoint(endpoint_id: str):
    cfg = _read()
    cfg["endpoints"] = [e for e in cfg.get("endpoints", []) if e["id"] != endpoint_id]
    if cfg.get("active_endpoint_id") == endpoint_id:
        rem = cfg["endpoints"]
        cfg["active_endpoint_id"] = rem[0]["id"] if rem else None
        cfg["active_model"] = None
    _write(cfg)
    return {"ok": True}


@app.post("/api/endpoints/{endpoint_id}/activate")
async def activate_endpoint(endpoint_id: str):
    cfg = _read()
    for ep in cfg.get("endpoints", []):
        if ep["id"] == endpoint_id:
            cfg["active_endpoint_id"] = endpoint_id
            cfg["active_model"] = None
            _write(cfg)
            return {"ok": True}
    raise HTTPException(404, "Endpoint not found")


# ── Models ────────────────────────────────────────────────────────────────────

@app.get("/api/models")
async def get_models():
    cfg = _read()
    ep = _active_ep(cfg)
    if not ep:
        return {"models": [], "error": "No active endpoint configured"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{ep['url']}/models", headers=_headers(ep))
            resp.raise_for_status()
        return {"models": [m["id"] for m in resp.json().get("data", [])]}
    except Exception as e:
        return {"models": [], "error": str(e)}


@app.post("/api/models/probe")
async def probe_endpoint(request: Request):
    data = await request.json()
    url = _normalize(data["url"])
    api_key = data.get("api_key", "")
    headers: dict = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{url}/models", headers=headers)
            resp.raise_for_status()
        return {"ok": True, "models": [m["id"] for m in resp.json().get("data", [])], "url": url}
    except Exception as e:
        return {"ok": False, "error": str(e), "models": []}


# ── Chat (SSE proxy with skill injection) ─────────────────────────────────────

@app.post("/api/chat/stream")
async def chat_stream(request: Request):
    body = await request.json()
    cfg = _read()
    ep = _active_ep(cfg)

    if not ep:
        raise HTTPException(400, "No endpoint configured. Type /setup to connect.")

    model = body.get("model") or cfg.get("active_model")
    if not model:
        raise HTTPException(400, "No model selected. Open the model picker to choose one.")

    messages = list(body.get("messages", []))

    # Inject enabled skills into the system prompt
    skills = _read_json(SKILLS_FILE)
    enabled = [s for s in skills if s.get("enabled", True) and (s.get("prompt") or s.get("description"))]
    if enabled:
        skills_ctx = "You have these skills and capabilities available:\n" + "\n".join(
            f"- {s['name']}: {s.get('prompt') or s.get('description', '')}" for s in enabled
        )
        if messages and messages[0].get("role") == "system":
            messages[0] = {**messages[0], "content": skills_ctx + "\n\n" + messages[0]["content"]}
        else:
            messages = [{"role": "system", "content": skills_ctx}] + messages

    payload: dict = {"model": model, "messages": messages, "stream": True}
    if "temperature" in body:
        payload["temperature"] = body["temperature"]
    if "max_tokens" in body:
        payload["max_tokens"] = body["max_tokens"]

    async def generate():
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                async with client.stream("POST", f"{ep['url']}/chat/completions", json=payload, headers=_headers(ep)) as resp:
                    if resp.status_code != 200:
                        err = await resp.aread()
                        yield f"data: {json.dumps({'error': err.decode()})}\n\n"
                        return
                    async for line in resp.aiter_lines():
                        if line:
                            yield f"{line}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})


# ── Memory ───────────────────────────────────────────────────────────────────

@app.get("/api/memory")
async def get_memory():
    return {"memories": _read_json(MEMORY_FILE)}


@app.post("/api/memory")
async def add_memory(request: Request):
    data = await request.json()
    text = (data.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "Memory text required")
    entry = {
        "id": str(uuid.uuid4()),
        "text": text,
        "category": data.get("category", "fact"),
        "timestamp": int(datetime.now().timestamp()),
        "pinned": bool(data.get("pinned", False)),
    }
    memories = _read_json(MEMORY_FILE)
    memories.append(entry)
    _write_json(MEMORY_FILE, memories)
    return {"ok": True, "memory": entry}


@app.put("/api/memory/{memory_id}")
async def update_memory(memory_id: str, request: Request):
    data = await request.json()
    memories = _read_json(MEMORY_FILE)
    for i, m in enumerate(memories):
        if m["id"] == memory_id:
            for f in ("text", "category", "pinned"):
                if f in data:
                    memories[i][f] = data[f].strip() if f == "text" else data[f]
            memories[i]["timestamp"] = int(datetime.now().timestamp())
            _write_json(MEMORY_FILE, memories)
            return {"ok": True, "memory": memories[i]}
    raise HTTPException(404, "Memory not found")


@app.delete("/api/memory/{memory_id}")
async def delete_memory(memory_id: str):
    memories = _read_json(MEMORY_FILE)
    updated = [m for m in memories if m["id"] != memory_id]
    if len(updated) == len(memories):
        raise HTTPException(404, "Memory not found")
    _write_json(MEMORY_FILE, updated)
    return {"ok": True}


@app.post("/api/memory/{memory_id}/pin")
async def pin_memory(memory_id: str, request: Request):
    data = await request.json()
    pinned = bool(data.get("pinned", True))
    memories = _read_json(MEMORY_FILE)
    for i, m in enumerate(memories):
        if m["id"] == memory_id:
            memories[i]["pinned"] = pinned
            _write_json(MEMORY_FILE, memories)
            return {"ok": True, "pinned": pinned}
    raise HTTPException(404, "Memory not found")


# ── Notes ────────────────────────────────────────────────────────────────────

@app.get("/api/notes")
async def get_notes():
    return {"notes": _read_json(NOTES_FILE)}


@app.post("/api/notes")
async def create_note(request: Request):
    data = await request.json()
    now = datetime.now().isoformat()
    note = {
        "id": str(uuid.uuid4()),
        "title": (data.get("title") or "Untitled Note").strip(),
        "body": data.get("body", ""),
        "pinned": bool(data.get("pinned", False)),
        "created_at": now,
        "updated_at": now,
    }
    notes = _read_json(NOTES_FILE)
    notes.insert(0, note)
    _write_json(NOTES_FILE, notes)
    return {"ok": True, "note": note}


@app.get("/api/notes/{note_id}")
async def get_note(note_id: str):
    notes = _read_json(NOTES_FILE)
    note = next((n for n in notes if n["id"] == note_id), None)
    if not note:
        raise HTTPException(404, "Note not found")
    return {"note": note}


@app.put("/api/notes/{note_id}")
async def update_note(note_id: str, request: Request):
    data = await request.json()
    notes = _read_json(NOTES_FILE)
    for i, n in enumerate(notes):
        if n["id"] == note_id:
            if "title" in data:
                notes[i]["title"] = (data["title"] or "Untitled Note").strip()
            if "body" in data:
                notes[i]["body"] = data["body"]
            if "pinned" in data:
                notes[i]["pinned"] = bool(data["pinned"])
            notes[i]["updated_at"] = datetime.now().isoformat()
            _write_json(NOTES_FILE, notes)
            return {"ok": True, "note": notes[i]}
    raise HTTPException(404, "Note not found")


@app.delete("/api/notes/{note_id}")
async def delete_note(note_id: str):
    notes = _read_json(NOTES_FILE)
    updated = [n for n in notes if n["id"] != note_id]
    if len(updated) == len(notes):
        raise HTTPException(404, "Note not found")
    _write_json(NOTES_FILE, updated)
    return {"ok": True}


# ── Tasks ────────────────────────────────────────────────────────────────────

@app.get("/api/tasks")
async def get_tasks():
    return {"tasks": _read_json(TASKS_FILE)}


@app.post("/api/tasks")
async def create_task(request: Request):
    data = await request.json()
    now = datetime.now().isoformat()
    task = {
        "id": str(uuid.uuid4()),
        "title": (data.get("title") or "New Task").strip(),
        "description": data.get("description", ""),
        "status": data.get("status", "todo"),
        "priority": data.get("priority", "medium"),
        "created_at": now,
        "updated_at": now,
    }
    tasks = _read_json(TASKS_FILE)
    tasks.append(task)
    _write_json(TASKS_FILE, tasks)
    return {"ok": True, "task": task}


@app.put("/api/tasks/{task_id}")
async def update_task(task_id: str, request: Request):
    data = await request.json()
    tasks = _read_json(TASKS_FILE)
    for i, t in enumerate(tasks):
        if t["id"] == task_id:
            for f in ("title", "description", "status", "priority"):
                if f in data:
                    tasks[i][f] = data[f]
            tasks[i]["updated_at"] = datetime.now().isoformat()
            _write_json(TASKS_FILE, tasks)
            return {"ok": True, "task": tasks[i]}
    raise HTTPException(404, "Task not found")


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str):
    tasks = _read_json(TASKS_FILE)
    updated = [t for t in tasks if t["id"] != task_id]
    if len(updated) == len(tasks):
        raise HTTPException(404, "Task not found")
    _write_json(TASKS_FILE, updated)
    return {"ok": True}


# ── Files ────────────────────────────────────────────────────────────────────

@app.get("/api/files")
async def get_files():
    return {"files": _read_json(FILES_FILE)}


@app.post("/api/files/upload")
async def upload_file(file: UploadFile = File(...)):
    _ensure()
    file_id = str(uuid.uuid4())
    safe_name = re.sub(r"[^\w.\-]", "_", file.filename or "upload")
    stored_name = f"{file_id}_{safe_name}"
    stored_path = UPLOADS_DIR / stored_name

    content = await file.read()
    with open(stored_path, "wb") as f:
        f.write(content)

    mime = file.content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    entry = {
        "id": file_id,
        "name": file.filename or "upload",
        "stored_name": stored_name,
        "size": len(content),
        "type": mime,
        "created_at": datetime.now().isoformat(),
    }
    files = _read_json(FILES_FILE)
    files.insert(0, entry)
    _write_json(FILES_FILE, files)
    return {"ok": True, "file": entry}


@app.delete("/api/files/{file_id}")
async def delete_file(file_id: str):
    files = _read_json(FILES_FILE)
    target = next((f for f in files if f["id"] == file_id), None)
    if not target:
        raise HTTPException(404, "File not found")
    stored_path = UPLOADS_DIR / target["stored_name"]
    if stored_path.exists():
        stored_path.unlink()
    _write_json(FILES_FILE, [f for f in files if f["id"] != file_id])
    return {"ok": True}


@app.get("/api/files/{file_id}/download")
async def download_file(file_id: str):
    files = _read_json(FILES_FILE)
    target = next((f for f in files if f["id"] == file_id), None)
    if not target:
        raise HTTPException(404, "File not found")
    stored_path = UPLOADS_DIR / target["stored_name"]
    if not stored_path.exists():
        raise HTTPException(404, "File data not found on disk")
    return FileResponse(path=str(stored_path), filename=target["name"],
                        media_type=target.get("type", "application/octet-stream"))


# ── Research (AI-generated structured reports) ────────────────────────────────

async def _do_search_for_research(query: str) -> list[dict]:
    """Internal web search helper used by background research jobs."""
    searxng = os.getenv("SEARXNG_INSTANCE", "http://localhost:8080").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{searxng}/search", params={"q": query, "format": "json", "language": "en"})
            r.raise_for_status()
            return [{"title": x.get("title",""), "url": x.get("url",""), "content": x.get("content","")}
                    for x in r.json().get("results", [])[:5] if x.get("url")]
    except Exception:
        pass
    try:
        ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
            r = await c.get(f"https://duckduckgo.com/html/?q={quote_plus(query)}", headers=ua)
            r.raise_for_status()
            html = r.text
        blocks = re.findall(r'<div class="result__body">(.*?)</div>\s*</div>', html, flags=re.DOTALL|re.IGNORECASE)[:5]
        out = []
        for block in blocks:
            lm = re.search(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, flags=re.DOTALL|re.IGNORECASE)
            if not lm:
                continue
            url = unescape(lm.group(1)).strip()
            title = re.sub(r"<[^>]+>"," ", lm.group(2)).strip()
            sm = re.search(r'class="result__snippet"[^>]*>(.*?)</[a-z]+>', block, flags=re.DOTALL|re.IGNORECASE)
            content = re.sub(r"<[^>]+>"," ", unescape(sm.group(1) if sm else "")).strip()
            if url and title:
                out.append({"title": title, "url": url, "content": content})
        return out
    except Exception:
        return []


async def _run_research_job(research_id: str):
    """Background task: uses active LLM to produce a structured research report."""
    try:
        sessions = _read_json(RESEARCH_FILE)
        entry = next((r for r in sessions if r["id"] == research_id), None)
        if not entry:
            return

        query = entry["query"]
        cfg = _read()
        ep = _active_ep(cfg)
        model = cfg.get("active_model")
        if not ep or not model:
            raise ValueError("No active endpoint or model — configure one in chat first")

        # Gather web context (best-effort)
        results_a = await _do_search_for_research(query)
        results_b = await _do_search_for_research(f"{query} analysis overview")
        all_results = (results_a + results_b)[:8]

        sources_block = ""
        if all_results:
            sources_block = "\n\n[Web Search Results]\n"
            for i, r in enumerate(all_results, 1):
                sources_block += f"\n[{i}] {r['title']}\nURL: {r.get('url','')}\n{r.get('content','')}\n"

        system_prompt = (
            "You are a thorough research analyst. Write a comprehensive, well-structured research report. "
            "Respond with ONLY a valid JSON object (no markdown fences) in this exact format:\n"
            '{"title":"<report title>","summary":"<2-3 sentence executive summary>",'
            '"sections":[{"title":"<section>","content":"<3-5 paragraphs>"}],'
            '"key_findings":["<finding 1>","<finding 2>","<finding 3>"],'
            '"sources":[{"title":"<name>","url":"<url or empty>","type":"<article|report|survey|website>"}]}\n'
            "Aim for 4-6 sections. Be analytical and specific."
        )

        async with httpx.AsyncClient(timeout=240) as client:
            resp = await client.post(
                f"{ep['url']}/chat/completions",
                json={"model": model, "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Research topic: {query}{sources_block}"},
                ], "stream": False, "temperature": 0.3},
                headers=_headers(ep),
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()

        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        parsed = json.loads(raw)
        llm_sources = parsed.get("sources", [])
        web_sources = [{"title": r["title"], "url": r.get("url",""), "type": "web"}
                       for r in all_results[:5]
                       if not any(l.get("url") == r.get("url") for l in llm_sources)]
        merged_sources = llm_sources + web_sources

        sessions = _read_json(RESEARCH_FILE)
        for i, r in enumerate(sessions):
            if r["id"] == research_id:
                sessions[i].update({
                    "status": "done",
                    "title": parsed.get("title", query),
                    "summary": parsed.get("summary", ""),
                    "sections": parsed.get("sections", []),
                    "key_findings": parsed.get("key_findings", []),
                    "sources": merged_sources,
                    "completed_at": datetime.now().isoformat(),
                    "error": None,
                })
                break
        _write_json(RESEARCH_FILE, sessions)

    except Exception as e:
        sessions = _read_json(RESEARCH_FILE)
        for i, r in enumerate(sessions):
            if r["id"] == research_id:
                sessions[i]["status"] = "error"
                sessions[i]["error"] = str(e)
                sessions[i]["completed_at"] = datetime.now().isoformat()
                break
        _write_json(RESEARCH_FILE, sessions)


@app.get("/api/research")
async def get_research_list():
    sessions = _read_json(RESEARCH_FILE)
    sessions.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"research": sessions}


@app.post("/api/research/start")
async def start_research(request: Request):
    data = await request.json()
    query = (data.get("query") or "").strip()
    if not query:
        raise HTTPException(400, "Research query required")
    cfg = _read()
    ep = _active_ep(cfg)
    model = cfg.get("active_model")
    if not ep or not model:
        raise HTTPException(400, "Configure an endpoint and model in Chat first")

    research_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    entry = {
        "id": research_id, "query": query, "status": "running",
        "title": query, "summary": "", "sections": [],
        "key_findings": [], "sources": [], "error": None,
        "created_at": now, "completed_at": None,
    }
    sessions = _read_json(RESEARCH_FILE)
    sessions.insert(0, entry)
    _write_json(RESEARCH_FILE, sessions)

    asyncio.create_task(_run_research_job(research_id))
    return {"ok": True, "id": research_id, "status": "running"}


@app.get("/api/research/{research_id}")
async def get_research_item(research_id: str):
    sessions = _read_json(RESEARCH_FILE)
    item = next((r for r in sessions if r["id"] == research_id), None)
    if not item:
        raise HTTPException(404, "Research not found")
    return {"research": item}


@app.delete("/api/research/{research_id}")
async def delete_research(research_id: str):
    sessions = _read_json(RESEARCH_FILE)
    updated = [r for r in sessions if r["id"] != research_id]
    if len(updated) == len(sessions):
        raise HTTPException(404, "Research not found")
    _write_json(RESEARCH_FILE, updated)
    return {"ok": True}


# ── Skills ────────────────────────────────────────────────────────────────────

@app.get("/api/skills")
async def get_skills():
    return {"skills": _read_json(SKILLS_FILE)}


@app.post("/api/skills")
async def create_skill(request: Request):
    data = await request.json()
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Skill name required")
    now = datetime.now().isoformat()
    skill = {
        "id": str(uuid.uuid4()),
        "name": name,
        "description": data.get("description", ""),
        "prompt": data.get("prompt", ""),
        "category": data.get("category", "general"),
        "icon": data.get("icon", "tasks"),
        "enabled": bool(data.get("enabled", True)),
        "created_at": now,
        "updated_at": now,
    }
    skills = _read_json(SKILLS_FILE)
    skills.append(skill)
    _write_json(SKILLS_FILE, skills)
    return {"ok": True, "skill": skill}


@app.put("/api/skills/{skill_id}")
async def update_skill(skill_id: str, request: Request):
    data = await request.json()
    skills = _read_json(SKILLS_FILE)
    for i, s in enumerate(skills):
        if s["id"] == skill_id:
            for f in ("name", "description", "prompt", "category", "icon", "enabled"):
                if f in data:
                    skills[i][f] = data[f]
            skills[i]["updated_at"] = datetime.now().isoformat()
            _write_json(SKILLS_FILE, skills)
            return {"ok": True, "skill": skills[i]}
    raise HTTPException(404, "Skill not found")


@app.post("/api/skills/{skill_id}/toggle")
async def toggle_skill(skill_id: str):
    skills = _read_json(SKILLS_FILE)
    for i, s in enumerate(skills):
        if s["id"] == skill_id:
            skills[i]["enabled"] = not bool(skills[i].get("enabled", True))
            skills[i]["updated_at"] = datetime.now().isoformat()
            _write_json(SKILLS_FILE, skills)
            return {"ok": True, "enabled": skills[i]["enabled"]}
    raise HTTPException(404, "Skill not found")


@app.delete("/api/skills/{skill_id}")
async def delete_skill(skill_id: str):
    skills = _read_json(SKILLS_FILE)
    updated = [s for s in skills if s["id"] != skill_id]
    if len(updated) == len(skills):
        raise HTTPException(404, "Skill not found")
    _write_json(SKILLS_FILE, updated)
    return {"ok": True}


# ── Static files (must be last) ───────────────────────────────────────────────
app.mount("/", StaticFiles(directory="static", html=True), name="static")
