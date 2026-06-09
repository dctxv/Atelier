"""Session + message repository (chat history persistence).

Moves chat sessions from client localStorage into the shared SQLite core, so
history survives a browser clear and follows the user across devices. The
session/message tables already existed; this is the repository that finally
uses them.

INVARIANT: a chat memory atom's source_id is a session id. add_message() (and
ensure()) INSERT-OR-IGNORE the session row before anything references it, so an
atom's source_id never dangles. That is what makes consolidation's orphan sweep
correct: deleting a session — and only that — leaves its atoms to be reclaimed.
"""
from __future__ import annotations

import uuid

from . import db

# Sentinel: lets update() tell "field omitted" apart from "explicitly set to NULL"
# (moving a chat OUT of a project sets project_id to None on purpose).
_UNSET = object()


def _session_row(r: dict) -> dict:
    return {"id": r["id"], "name": r["name"], "model": r["model"],
            "project_id": r.get("project_id"),
            "created_at": r["created_at"], "updated_at": r["updated_at"]}


def _message_row(r: dict) -> dict:
    return {"id": r["id"], "role": r["role"], "content": r["content"],
            "model": r["model"], "created_at": r["created_at"]}


async def list_sessions(limit: int = 200, project_id: str | None = None,
                        scope: str = "global") -> list[dict]:
    """List sessions, newest first.

    project_id set    → only that project's sessions.
    project_id None   → scope='global' (default) returns unassigned sessions
                        (project_id IS NULL); scope='all' returns everything.

    The 'global' default keeps the main chat tab free of project conversations
    without the frontend having to change how it calls /api/sessions.
    """
    if project_id is not None:
        rows = await db.fetchall(
            "SELECT * FROM session WHERE project_id=? ORDER BY updated_at DESC LIMIT ?",
            (project_id, limit),
        )
    elif scope == "all":
        rows = await db.fetchall(
            "SELECT * FROM session ORDER BY updated_at DESC LIMIT ?", (limit,))
    else:  # 'global'
        rows = await db.fetchall(
            "SELECT * FROM session WHERE project_id IS NULL ORDER BY updated_at DESC LIMIT ?",
            (limit,))
    return [_session_row(r) for r in rows]


async def get_session(session_id: str) -> dict | None:
    row = await db.fetchone("SELECT * FROM session WHERE id=?", (session_id,))
    if not row:
        return None
    msgs = await db.fetchall(
        "SELECT * FROM message WHERE session_id=? ORDER BY created_at, rowid", (session_id,)
    )
    out = _session_row(row)
    out["messages"] = [_message_row(m) for m in msgs]
    return out


async def _bare(session_id: str) -> dict | None:
    row = await db.fetchone("SELECT * FROM session WHERE id=?", (session_id,))
    return _session_row(row) if row else None


async def create(name: str = "New chat", model: str | None = None,
                 session_id: str | None = None, project_id: str | None = None) -> dict:
    sid = session_id or str(uuid.uuid4())
    ts = db.now()
    await db.execute(
        "INSERT OR IGNORE INTO session(id, name, model, project_id, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?)",
        (sid, (name or "New chat").strip()[:120], model, project_id, ts, ts),
    )
    return await _bare(sid)


async def update(session_id: str, *, name=None, model=None, project_id=_UNSET) -> dict | None:
    existing = await db.fetchone("SELECT * FROM session WHERE id=?", (session_id,))
    if not existing:
        return None
    new_project = existing.get("project_id") if project_id is _UNSET else project_id
    await db.execute(
        "UPDATE session SET name=?, model=?, project_id=?, updated_at=? WHERE id=?",
        ((name.strip()[:120] if isinstance(name, str) else existing["name"]),
         model if model is not None else existing["model"],
         new_project, db.now(), session_id),
    )
    return await _bare(session_id)


async def delete(session_id: str) -> bool:
    existing = await db.fetchone("SELECT id FROM session WHERE id=?", (session_id,))
    if not existing:
        return False

    def op(conn):
        conn.execute("DELETE FROM message WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM session WHERE id=?", (session_id,))

    await db.write(op)
    return True


async def add_message(session_id: str, role: str, content: str, model: str | None = None) -> str:
    """Append a message and bump updated_at, in one transaction. INSERT-OR-IGNOREs
    the session first so atom source_ids never dangle (the core invariant)."""
    mid = str(uuid.uuid4())
    ts = db.now()

    def op(conn):
        conn.execute(
            "INSERT OR IGNORE INTO session(id, name, model, created_at, updated_at) VALUES(?,?,?,?,?)",
            (session_id, "New chat", model, ts, ts),
        )
        conn.execute(
            "INSERT INTO message(id, session_id, role, content, model, created_at) VALUES(?,?,?,?,?,?)",
            (mid, session_id, role, content, model, ts),
        )
        conn.execute("UPDATE session SET updated_at=? WHERE id=?", (ts, session_id))

    await db.write(op)
    return mid


async def import_sessions(sessions: list[dict]) -> int:
    """One-time migration: bulk-insert localStorage sessions + their messages."""
    n = 0
    for s in sessions:
        sid = s.get("id") or str(uuid.uuid4())
        name = str(s.get("name") or "New chat")[:120]
        model = s.get("model")
        created = s.get("createdAt") or s.get("created_at") or db.now()
        if isinstance(created, (int, float)) and created > 10_000_000_000:
            created = int(created / 1000)   # JS ms -> epoch seconds
        msgs = s.get("messages") or []

        def op(conn, sid=sid, name=name, model=model, created=int(created), msgs=msgs):
            conn.execute(
                "INSERT OR IGNORE INTO session(id, name, model, created_at, updated_at) VALUES(?,?,?,?,?)",
                (sid, name, model, created, created),
            )
            last = created
            for m in msgs:
                role, content = m.get("role"), m.get("content")
                if role not in ("user", "assistant") or content is None:
                    continue
                last += 1   # deterministic ordering for same-second messages
                conn.execute(
                    "INSERT INTO message(id, session_id, role, content, model, created_at) VALUES(?,?,?,?,?,?)",
                    (str(uuid.uuid4()), sid, role, content, m.get("model"), last),
                )
            conn.execute("UPDATE session SET updated_at=? WHERE id=?", (last, sid))

        await db.write(op)
        n += 1
    return n
