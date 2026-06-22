"""Commitment repository.

A commitment is the review-gated bridge from "thinking" to "doing":
chat/extraction proposes it, the user confirms it, and only then do we create
the task that carries it forward.
"""
from __future__ import annotations

import json
import uuid

from . import db, tasks


def _decode(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _row(r: dict) -> dict:
    return {
        "id": r["id"],
        "title": r["title"],
        "description": r.get("description") or "",
        "status": r.get("status") or "proposed",
        "source_kind": r.get("source_kind"),
        "source_id": r.get("source_id"),
        "atom_id": r.get("atom_id"),
        "task_id": r.get("task_id"),
        "context": _decode(r.get("context_json")),
        "created_at": r.get("created_at"),
        "updated_at": r.get("updated_at"),
        "confirmed_at": r.get("confirmed_at"),
        "rejected_at": r.get("rejected_at"),
        "atom_text": r.get("atom_text"),
        "task_status": r.get("task_status"),
    }


async def get(commitment_id: str) -> dict | None:
    row = await db.fetchone(
        "SELECT c.*, a.text AS atom_text, t.status AS task_status "
        "FROM commitment c "
        "LEFT JOIN memory_atom a ON a.id=c.atom_id "
        "LEFT JOIN task t ON t.id=c.task_id "
        "WHERE c.id=?",
        (commitment_id,),
    )
    return _row(row) if row else None


async def list_commitments(status: str | None = "proposed",
                           limit: int = 100) -> list[dict]:
    params: list = []
    where = ""
    if status and status != "all":
        where = "WHERE c.status=?"
        params.append(status)
    params.append(limit)
    rows = await db.fetchall(
        "SELECT c.*, a.text AS atom_text, t.status AS task_status "
        "FROM commitment c "
        "LEFT JOIN memory_atom a ON a.id=c.atom_id "
        "LEFT JOIN task t ON t.id=c.task_id "
        f"{where} "
        "ORDER BY CASE c.status WHEN 'proposed' THEN 0 WHEN 'active' THEN 1 "
        "WHEN 'done' THEN 2 ELSE 3 END, c.created_at DESC LIMIT ?",
        tuple(params),
    )
    return [_row(r) for r in rows]


async def propose(
    *,
    title: str,
    description: str = "",
    source_kind: str = "chat",
    source_id: str | None = None,
    atom_id: str | None = None,
    context: dict | None = None,
) -> dict:
    title = (title or "New commitment").strip()[:240]
    description = (description or "").strip()

    if atom_id:
        existing = await db.fetchone(
            "SELECT * FROM commitment WHERE atom_id=? "
            "AND status IN ('proposed','active','done') LIMIT 1",
            (atom_id,),
        )
        if existing:
            return await get(existing["id"])

    cid = str(uuid.uuid4())
    ts = db.now()
    await db.execute(
        "INSERT INTO commitment("
        "id, title, description, status, source_kind, source_id, atom_id, "
        "context_json, created_at, updated_at"
        ") VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            cid, title, description, "proposed", source_kind, source_id, atom_id,
            json.dumps(context or {}), ts, ts,
        ),
    )
    return await get(cid)


async def propose_from_atom(
    atom: dict,
    session_id: str | None,
    *,
    user_text: str = "",
    assistant_text: str = "",
) -> dict | None:
    if not atom:
        return None
    title = (atom.get("text") or "").strip()
    if not title:
        return None
    context = {
        "origin": "chat_extraction",
        "atom_ids": [atom.get("id")] if atom.get("id") else [],
        "source_session_id": session_id,
    }
    if user_text:
        context["user_text"] = user_text[:1000]
    if assistant_text:
        context["assistant_text"] = assistant_text[:1000]
    return await propose(
        title=title,
        description=f"Proposed from session {session_id or 'unknown'}",
        source_kind="chat",
        source_id=session_id,
        atom_id=atom.get("id"),
        context=context,
    )


async def confirm(commitment_id: str) -> dict | None:
    existing = await get(commitment_id)
    if not existing or existing["status"] == "rejected":
        return None

    task_id = existing.get("task_id")
    if not task_id:
        task = await tasks.create({
            "title": existing["title"],
            "description": existing.get("description") or "Confirmed commitment",
            "status": "todo",
            "priority": "medium",
            "source_kind": "commitment",
            "source_id": commitment_id,
        })
        task_id = task["id"]

    ts = db.now()
    await db.execute(
        "UPDATE commitment SET status='active', task_id=?, confirmed_at=COALESCE(confirmed_at, ?), "
        "updated_at=? WHERE id=?",
        (task_id, ts, ts, commitment_id),
    )
    return await get(commitment_id)


async def reject(commitment_id: str) -> dict | None:
    existing = await get(commitment_id)
    if not existing or existing.get("task_id"):
        return None
    ts = db.now()
    await db.execute(
        "UPDATE commitment SET status='rejected', rejected_at=?, updated_at=? WHERE id=?",
        (ts, ts, commitment_id),
    )
    return await get(commitment_id)


async def sync_task_status(task_id: str, task_status: str) -> None:
    """Keep the commitment lifecycle aligned after the task is completed."""
    if task_status not in ("done", "completed"):
        return
    await db.execute(
        "UPDATE commitment SET status='done', updated_at=? WHERE task_id=?",
        (db.now(), task_id),
    )
