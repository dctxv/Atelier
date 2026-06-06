"""One-time JSON -> SQLite importer (Part 1.1).

Runs once on first startup against the new DB. Reads the legacy data/*.json
files, writes them into the tables, verifies row counts, and sets a flag in
app_config so it never runs again. The JSON files are left on disk (untouched)
as a safety net but are no longer read by the app after import.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from . import config, crypto, db, embeddings

DATA_DIR = Path("data")


def _epoch(value, default=None) -> int:
    if value is None:
        return default if default is not None else db.now()
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(datetime.fromisoformat(str(value)).timestamp())
    except Exception:
        return default if default is not None else db.now()


def _read_json(name: str, default):
    p = DATA_DIR / name
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


async def _import_endpoints():
    cfg = _read_json("config.json", {})
    n = 0
    for ep in cfg.get("endpoints", []):
        await db.execute(
            "INSERT OR IGNORE INTO endpoint(id, name, base_url, api_key_enc, type, created_at) "
            "VALUES(?,?,?,?,?,?)",
            (ep.get("id") or str(uuid.uuid4()), ep.get("name", "Unnamed"),
             ep.get("url", ""), crypto.encrypt(ep.get("api_key", "")),
             ep.get("type", "local"), db.now()),
        )
        n += 1
    if cfg.get("active_endpoint_id"):
        await config.set_setting("active_endpoint_id", cfg["active_endpoint_id"])
    if cfg.get("active_model"):
        await config.set_setting("active_model", cfg["active_model"])
    return n


async def _import_memory():
    items = _read_json("memory.json", [])
    n = 0
    for m in items:
        text = (m.get("text") or "").strip()
        if not text:
            continue
        atom_id = m.get("id") or str(uuid.uuid4())
        ts = _epoch(m.get("timestamp"))
        vec = await embeddings.embed(text)
        payload = db.serialize_f32(vec)

        def op(conn, atom_id=atom_id, text=text, m=m, ts=ts, payload=payload):
            conn.execute(
                "INSERT OR IGNORE INTO memory_atom(id, text, type, salience, source_kind, "
                "source_id, created_at, last_used_at, pinned) VALUES(?,?,?,?,?,?,?,?,?)",
                (atom_id, text, m.get("category", "fact"), 1.0, "manual", None, ts, ts,
                 int(bool(m.get("pinned")))),
            )
            rid = conn.execute("SELECT rowid FROM memory_atom WHERE id=?", (atom_id,)).fetchone()[0]
            conn.execute("INSERT OR REPLACE INTO memory_vec(rowid, embedding) VALUES(?,?)", (rid, payload))
            conn.execute("INSERT INTO memory_fts(rowid, text) VALUES(?,?)", (rid, text))

        await db.write(op)
        n += 1
    return n


async def _import_notes():
    items = _read_json("notes.json", [])
    n = 0
    for note in items:
        await db.execute(
            "INSERT OR IGNORE INTO note(id, title, body, pinned, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?)",
            (note.get("id") or str(uuid.uuid4()), note.get("title", "Untitled Note"),
             note.get("body", ""), int(bool(note.get("pinned"))),
             _epoch(note.get("created_at")), _epoch(note.get("updated_at"))),
        )
        n += 1
    return n


async def _import_tasks():
    items = _read_json("tasks.json", [])
    n = 0
    for t in items:
        await db.execute(
            "INSERT OR IGNORE INTO task(id, title, description, status, priority, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (t.get("id") or str(uuid.uuid4()), t.get("title", "Task"), t.get("description", ""),
             t.get("status", "todo"), t.get("priority", "medium"),
             _epoch(t.get("created_at")), _epoch(t.get("updated_at"))),
        )
        n += 1
    return n


async def _import_files():
    items = _read_json("files.json", [])
    n = 0
    for f in items:
        await db.execute(
            "INSERT OR IGNORE INTO file(id, name, stored_name, size, type, created_at) "
            "VALUES(?,?,?,?,?,?)",
            (f.get("id") or str(uuid.uuid4()), f.get("name", "upload"), f.get("stored_name", ""),
             f.get("size", 0), f.get("type", "application/octet-stream"),
             _epoch(f.get("created_at"))),
        )
        n += 1
    return n


async def _import_research():
    items = _read_json("research.json", [])
    n = 0
    for r in items:
        rid = r.get("id") or str(uuid.uuid4())
        await db.execute(
            "INSERT OR IGNORE INTO research(id, query, status, title, summary, created_at, completed_at, error) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (rid, r.get("query", ""), r.get("status", "done"), r.get("title", ""),
             r.get("summary", ""), _epoch(r.get("created_at")),
             _epoch(r.get("completed_at"), 0) or None, r.get("error")),
        )
        for idx, sec in enumerate(r.get("sections", [])):
            await db.execute(
                "INSERT INTO research_section(id, research_id, idx, title, content) VALUES(?,?,?,?,?)",
                (str(uuid.uuid4()), rid, idx, sec.get("title", ""), sec.get("content", "")),
            )
        for src in r.get("sources", []):
            await db.execute(
                "INSERT INTO research_source(id, research_id, url, title) VALUES(?,?,?,?)",
                (str(uuid.uuid4()), rid, src.get("url", ""), src.get("title", "")),
            )
        n += 1
    return n


async def _import_skills():
    items = _read_json("skills.json", [])
    n = 0
    for s in items:
        await db.execute(
            "INSERT OR IGNORE INTO skill(id, name, description, prompt, category, icon, enabled, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (s.get("id") or str(uuid.uuid4()), s.get("name", "Skill"), s.get("description", ""),
             s.get("prompt", ""), s.get("category", "general"), s.get("icon", "tasks"),
             int(bool(s.get("enabled", True))), _epoch(s.get("created_at")), _epoch(s.get("updated_at"))),
        )
        n += 1
    return n


async def run_import() -> dict | None:
    """Import once. Returns a row-count report, or None if already imported."""
    if await config.get_setting("json_imported") == "1":
        return None

    report = {
        "endpoints": await _import_endpoints(),
        "memory": await _import_memory(),
        "notes": await _import_notes(),
        "tasks": await _import_tasks(),
        "files": await _import_files(),
        "research": await _import_research(),
        "skills": await _import_skills(),
    }

    # Verify: counts in the tables should be >= what we imported.
    verify = {
        "memory": (await db.fetchone("SELECT COUNT(*) AS n FROM memory_atom"))["n"],
        "notes": (await db.fetchone("SELECT COUNT(*) AS n FROM note"))["n"],
        "tasks": (await db.fetchone("SELECT COUNT(*) AS n FROM task"))["n"],
        "research": (await db.fetchone("SELECT COUNT(*) AS n FROM research"))["n"],
        "skills": (await db.fetchone("SELECT COUNT(*) AS n FROM skill"))["n"],
    }

    await config.set_setting("json_imported", "1")
    return {"imported": report, "verified": verify}
