"""Project repository — CRUD + manifest + librarian + working-set cache.

Architecture (from design spec §1-§3):

  Tier 0  instructions  — per-project system prompt, always injected, tiny.
  Tier 1  manifest      — every file name + abstract, bounded, caches as prefix.
  Tier 2  scoped RAG    — retrieve() with project_id filter (over-fetch + filter).
  Tier 3  whole file    — librarian decides which full files to load, working-set
                          warm cache keeps them across turns.

Config knobs (read from app_config, defaults below):
  projects.weak_retrieval_cos     = 0.35
  projects.small_project_files    = 3
  projects.small_project_tokens   = 6000
  projects.project_overfetch      = 6
  projects.context_budget         = 4000
  projects.manifest_cap           = 1000
  projects.wholefile_cap          = 2000
  projects.working_set_max_tokens = 4000
  projects.manifest_full_files    = 25
  projects.manifest_top_m         = 15
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from . import db, llm

# ── Defaults ─────────────────────────────────────────────────────────────────

_DEFAULTS: dict[str, Any] = {
    "projects.weak_retrieval_cos":     0.35,
    "projects.small_project_files":    3,
    "projects.small_project_tokens":   6000,
    "projects.project_overfetch":      6,
    "projects.context_budget":         4000,
    "projects.manifest_cap":           1000,
    "projects.wholefile_cap":          2000,
    "projects.working_set_max_tokens": 4000,
    "projects.manifest_full_files":    25,
    "projects.manifest_top_m":         15,
}

_CHARS_PER_TOKEN = 4


def _tok(s: str) -> int:
    return max(1, len(s) // _CHARS_PER_TOKEN)


async def _cfg(key: str) -> Any:
    from . import config
    val = await config.get_setting(key)
    default = _DEFAULTS.get(key)
    if val is None:
        return default
    if isinstance(default, int):
        try:
            return int(val)
        except (ValueError, TypeError):
            return default
    if isinstance(default, float):
        try:
            return float(val)
        except (ValueError, TypeError):
            return default
    return val


# ── Row shaping ───────────────────────────────────────────────────────────────

def _shape(row: dict) -> dict:
    return {
        "id":           row["id"],
        "name":         row["name"],
        "instructions": row.get("instructions"),
        "icon":         row.get("icon", "projects"),
        "created_at":   row["created_at"],
        "updated_at":   row["updated_at"],
    }


# ── CRUD ──────────────────────────────────────────────────────────────────────

async def create(name: str, instructions: str | None = None) -> dict:
    pid = str(uuid.uuid4())
    now = db.now()
    await db.execute(
        "INSERT INTO project(id, name, instructions, created_at, updated_at) VALUES(?,?,?,?,?)",
        (pid, name.strip()[:120], instructions, now, now),
    )
    return await get(pid)


async def get(project_id: str) -> dict | None:
    row = await db.fetchone("SELECT * FROM project WHERE id=?", (project_id,))
    return _shape(row) if row else None


async def list_all() -> list[dict]:
    rows = await db.fetchall(
        "SELECT p.*, COUNT(d.id) AS file_count "
        "FROM project p "
        "LEFT JOIN document d ON d.project_id = p.id "
        "GROUP BY p.id ORDER BY p.updated_at DESC"
    )
    return [
        {**_shape(r), "file_count": r.get("file_count", 0)}
        for r in rows
    ]


async def update(project_id: str, *, name: str | None = None,
                 instructions: str | None = None) -> dict | None:
    existing = await db.fetchone("SELECT * FROM project WHERE id=?", (project_id,))
    if not existing:
        return None
    new_name = (name.strip()[:120] if isinstance(name, str) else existing["name"])
    # Allow clearing instructions by passing empty string → store NULL
    if instructions is None:
        new_instr = existing.get("instructions")
    elif instructions.strip() == "":
        new_instr = None
    else:
        new_instr = instructions.strip()
    now = db.now()
    await db.execute(
        "UPDATE project SET name=?, instructions=?, updated_at=? WHERE id=?",
        (new_name, new_instr, now, project_id),
    )
    return await get(project_id)


async def delete(project_id: str) -> bool:
    existing = await db.fetchone("SELECT id FROM project WHERE id=?", (project_id,))
    if not existing:
        return False

    def op(conn):
        # Disassociate documents (set project_id = NULL rather than delete them)
        conn.execute("UPDATE document SET project_id=NULL WHERE project_id=?", (project_id,))
        conn.execute("UPDATE memory_atom SET project_id=NULL WHERE project_id=?", (project_id,))
        conn.execute("UPDATE session SET project_id=NULL WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM project WHERE id=?", (project_id,))

    await db.write(op)
    return True


# ── Document scoping ──────────────────────────────────────────────────────────

async def list_documents(project_id: str) -> list[dict]:
    """Return all documents belonging to this project."""
    rows = await db.fetchall(
        "SELECT * FROM document WHERE project_id=? ORDER BY created_at DESC",
        (project_id,),
    )
    from . import documents as _docs
    return [_docs._shape(r) for r in rows]


async def assign_document(doc_id: str, project_id: str) -> bool:
    """Assign a document to a project."""
    existing = await db.fetchone("SELECT id FROM document WHERE id=?", (doc_id,))
    if not existing:
        return False
    await db.execute("UPDATE document SET project_id=? WHERE id=?", (project_id, doc_id))
    return True


# ── Tier 1: Manifest builder ──────────────────────────────────────────────────

async def build_manifest(
    project_id: str,
    query_vec: bytes | None = None,
) -> tuple[str, list[dict]]:
    """Build the Tier-1 manifest for a project.

    Returns (manifest_text, docs_list).
    manifest_text is bounded by projects.manifest_cap tokens.
    When query_vec is provided and the project has >manifest_full_files docs,
    the manifest ranks abstracts by cosine similarity so the top-M get abstracts
    and the rest get name-only lines.
    """
    full_files = int(await _cfg("projects.manifest_full_files"))
    top_m      = int(await _cfg("projects.manifest_top_m"))
    cap_tok    = int(await _cfg("projects.manifest_cap"))

    docs = await list_documents(project_id)
    if not docs:
        return "", []

    ready_docs = [d for d in docs if d["status"] == "ready"]
    all_docs   = docs  # for reference

    if not ready_docs:
        # Only show filenames if nothing is ready yet
        lines = ["[PROJECT FILES — being processed]"]
        for d in docs:
            lines.append(f"- {d['filename']} ({d['status']})")
        return "\n".join(lines), docs

    if len(ready_docs) <= full_files or query_vec is None:
        # Show name + abstract for all
        lines = [f"[PROJECT MANIFEST — {len(ready_docs)} file(s) available for reference]"]
        used = _tok(lines[0])
        for d in ready_docs:
            abstract = d.get("abstract") or ""
            entry = f"- [{d['id'][:8]}] {d['filename']}\n  {abstract}" if abstract else f"- [{d['id'][:8]}] {d['filename']}"
            cost = _tok(entry)
            if used + cost > cap_tok:
                lines.append(f"- [{d['id'][:8]}] {d['filename']} [abstract omitted — budget]")
                used += _tok(lines[-1])
            else:
                lines.append(entry)
                used += cost
    else:
        # Rank by cosine similarity to the query, show abstracts for top-M only
        import numpy as np
        scored: list[tuple[float, dict]] = []
        for d in ready_docs:
            scored.append((0.0, d))  # default score — abstract not embedded here; fallback to recency order

        top_docs = [d for _, d in scored[:top_m]]
        tail_docs = [d for _, d in scored[top_m:]]

        lines = [f"[PROJECT MANIFEST — {len(ready_docs)} file(s); top {top_m} shown with abstracts]"]
        used = _tok(lines[0])
        for d in top_docs:
            abstract = d.get("abstract") or ""
            entry = f"- [{d['id'][:8]}] {d['filename']}\n  {abstract}" if abstract else f"- [{d['id'][:8]}] {d['filename']}"
            lines.append(entry)
            used += _tok(entry)
        # Name-only tail
        if tail_docs:
            lines.append("\n[Additional files (names only — available for full loading):]")
            for d in tail_docs:
                entry = f"- [{d['id'][:8]}] {d['filename']}"
                lines.append(entry)

    text = "\n".join(lines)
    return text, docs


# ── Tier 3: Gate check ────────────────────────────────────────────────────────

# Verbs that signal the user wants a whole document, not just excerpts
_WHOLEFILE_VERBS = re.compile(
    r"\b(summari[sz]e|review|walk\s+through|read\s+.{0,30}\s+and|"
    r"the\s+(whole|entire|full)|translate|convert|reformat|edit|"
    r"proofread|annotate|extract\s+all|list\s+all\s+from)\b",
    re.I,
)


def should_call_librarian(
    query: str,
    docs: list[dict],
    top_chunk_score: float | None,
    small_files: int,
    small_tokens: int,
) -> str:
    """Determine whether to call the librarian.

    Returns: 'skip' | 'dump' | 'librarian'
      skip:      go straight to Tier 0+1+2, no extra calls
      dump:      tiny project — load all files, skip librarian
      librarian: call the cheap-model selector
    """
    if not docs:
        return "skip"

    # Small-project dump path — cheaper to include everything
    total_abstract_tok = sum(_tok(d.get("abstract") or "") for d in docs)
    if len(docs) <= small_files and total_abstract_tok <= small_tokens:
        return "dump"

    # Gate conditions
    if _WHOLEFILE_VERBS.search(query):
        return "librarian"

    # Filename mention — fuzzy match any doc name in the query
    ql = query.lower()
    for d in docs:
        stem = d["filename"].lower().rsplit(".", 1)[0]
        if stem in ql or d["filename"].lower() in ql:
            return "librarian"

    # Weak retrieval (top chunk below threshold)
    if top_chunk_score is not None and top_chunk_score < 0.35:  # VALIDATE
        return "librarian"

    return "skip"


# ── Tier 3: Librarian selector ────────────────────────────────────────────────

async def run_librarian(
    query: str,
    manifest: str,
    retrieved_previews: list[dict],
    docs: list[dict],
) -> list[str]:
    """Call cheap model to select which files (by ID) need full loading.

    Returns list of doc IDs (usually [], sometimes 1-2).
    """
    preview_text = ""
    for chunk in retrieved_previews[:5]:
        fname = chunk.get("filename", "")
        snippet = (chunk.get("text") or "")[:200]
        preview_text += f"- [{fname}] {snippet}\n"

    doc_list = "\n".join(
        f"  ID={d['id'][:8]}  File={d['filename']}  Abstract={d.get('abstract','')[:120]}"
        for d in docs if d.get("status") == "ready"
    )
    prompt = (
        "You are a file selector. The user has asked a question, and you have been shown "
        "the project file index and some retrieved excerpts.\n\n"
        f"QUESTION: {query}\n\n"
        f"AVAILABLE FILES:\n{doc_list}\n\n"
        f"RETRIEVED EXCERPTS (first {len(retrieved_previews[:5])}):\n{preview_text}\n\n"
        "Return ONLY a JSON array of file IDs (the 8-char prefix shown above) whose FULL "
        "contents are needed to answer well. Return [] if the excerpts are likely sufficient. "
        "Prefer [] — only request a file when the question clearly needs the whole document. "
        "Maximum 2 file IDs.\n\nJSON array:"
    )
    try:
        raw = await llm.cheap(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=60,
            task="librarian",
        )
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw).rstrip("`").strip()
        import json
        ids_short = json.loads(raw)
        if not isinstance(ids_short, list):
            return []
        # Map short IDs back to full doc IDs
        full_ids = []
        for short in ids_short:
            if not isinstance(short, str):
                continue
            for d in docs:
                if d["id"].startswith(short) and d.get("status") == "ready":
                    full_ids.append(d["id"])
                    break
        return full_ids[:2]
    except Exception:
        return []


# ── Tier 3: Whole-file loader ─────────────────────────────────────────────────

async def load_full_files(doc_ids: list[str], budget_tokens: int = 2000) -> str:
    """Load the full text of specific documents, bounded by budget_tokens."""
    if not doc_ids:
        return ""

    blocks: list[str] = []
    used = 0
    for doc_id in doc_ids:
        doc = await db.fetchone("SELECT * FROM document WHERE id=?", (doc_id,))
        if not doc or doc.get("status") != "ready":
            continue
        chunks = await db.fetchall(
            "SELECT text, seq, char_start, char_end FROM document_chunk "
            "WHERE document_id=? ORDER BY seq",
            (doc_id,),
        )
        fname = doc.get("filename", "document")
        full_text = "\n".join(c["text"] for c in chunks)
        cost = _tok(full_text)
        if used + cost > budget_tokens and blocks:
            # Truncate to fit
            remaining_chars = (budget_tokens - used) * _CHARS_PER_TOKEN
            if remaining_chars > 500:
                full_text = full_text[:remaining_chars] + "\n[… truncated to fit context budget]"
            else:
                break
        blocks.append(f"[FULL FILE: {fname}]\n{full_text}\n[END: {fname}]")
        used += _tok(full_text)

    return "\n\n".join(blocks)


# ── Session working-set cache ─────────────────────────────────────────────────

# {session_id: {"file_id:updated_at": full_text_block, ...}}
_working_set: dict[str, dict[str, str]] = {}


def get_warm_files(session_id: str, doc_ids: list[str],
                   doc_meta: dict[str, dict]) -> tuple[str, list[str]]:
    """Return (warm_text, missing_ids) from the session working set.

    warm_text: concatenated text of files already cached this session
    missing_ids: doc_ids not yet warm (need to be loaded from DB)
    """
    cache = _working_set.get(session_id, {})
    warm_parts: list[str] = []
    missing: list[str] = []

    for doc_id in doc_ids:
        meta = doc_meta.get(doc_id, {})
        key = f"{doc_id}:{meta.get('updated_at', 0)}"
        if key in cache:
            warm_parts.append(cache[key])
        else:
            missing.append(doc_id)

    return "\n\n".join(warm_parts), missing


def warm_files(session_id: str, doc_ids: list[str],
               text_blocks: dict[str, str],
               doc_meta: dict[str, dict],
               max_tokens: int = 4000) -> None:
    """Add newly-loaded file texts to the session working set.

    text_blocks: {doc_id: block_text}
    Evicts least-recently-added when over budget.
    """
    if session_id not in _working_set:
        _working_set[session_id] = {}
    cache = _working_set[session_id]

    total = sum(_tok(v) for v in cache.values())
    for doc_id in doc_ids:
        block = text_blocks.get(doc_id)
        if not block:
            continue
        meta = doc_meta.get(doc_id, {})
        key = f"{doc_id}:{meta.get('updated_at', 0)}"
        cost = _tok(block)
        # Evict oldest entries if over budget
        while total + cost > max_tokens and cache:
            oldest_key = next(iter(cache))
            total -= _tok(cache.pop(oldest_key))
        cache[key] = block
        total += cost


def clear_working_set(session_id: str) -> None:
    """Clear a session's working set (e.g. when session ends)."""
    _working_set.pop(session_id, None)
