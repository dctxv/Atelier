"""Memory question / uncertainty register — Living Memory v2 (M4).

Open questions are conflicts, gaps, or stale checks surfaced to the user
via the Review tab. They are throttled and never interrupt chat directly
(except for the single narrow inline clarification path in routers/chat.py).
"""
from __future__ import annotations

import json
import uuid

from . import db, memory

# Hard throttle constants — all [VALIDATE] against real usage
MAX_OPEN_QUESTIONS       = 10
DISMISS_COOLDOWN_DAYS    = 30
PER_PREDICATE_COOLDOWN_S = 7 * 86400

HIGH_IMPORTANCE_PREDICATES = frozenset({
    "employer", "lives_in", "partner", "name", "job_title",
})


async def open_count() -> int:
    row = await db.fetchone(
        "SELECT COUNT(*) AS n FROM memory_question WHERE status='open'"
    )
    return row["n"] if row else 0


async def can_open_question(kind: str, atom_ids: list[str]) -> bool:
    """Check throttle limits before opening a new question."""
    n = await open_count()
    if n >= MAX_OPEN_QUESTIONS:
        return False
    return True


async def open_question(
    kind: str,
    atom_ids: list[str],
    prompt_text: str,
) -> str | None:
    """Create an open question if throttle allows. Returns question id or None."""
    if not await can_open_question(kind, atom_ids):
        return None

    qid = str(uuid.uuid4())
    ts = db.now()
    await db.execute(
        "INSERT INTO memory_question(id, kind, atom_ids, prompt_text, status, created_at) "
        "VALUES(?,?,?,?,?,?)",
        (qid, kind, json.dumps(atom_ids), prompt_text, "open", ts),
    )
    return qid


async def list_questions(status: str = "open") -> list[dict]:
    rows = await db.fetchall(
        "SELECT * FROM memory_question WHERE status=? ORDER BY created_at DESC",
        (status,),
    )
    result = []
    for r in rows:
        q = dict(r)
        q["atom_ids"] = json.loads(q.get("atom_ids") or "[]")
        if q.get("resolution"):
            try:
                q["resolution"] = json.loads(q["resolution"])
            except Exception:
                pass
        # Attach atom details for UI rendering
        q["atoms"] = []
        for aid in q["atom_ids"]:
            atom = await memory.get_atom(aid)
            if atom:
                q["atoms"].append(atom)
        result.append(q)
    return result


async def resolve_question(
    question_id: str,
    choice: str,            # confirm_a | confirm_b | both_true | neither | dismiss
    atom_id: str | None = None,
    detail: str | None = None,
) -> bool:
    """Resolve a question with a user choice."""
    row = await db.fetchone(
        "SELECT * FROM memory_question WHERE id=?", (question_id,)
    )
    if not row or row["status"] != "open":
        return False

    atom_ids = json.loads(row.get("atom_ids") or "[]")
    ts = db.now()
    resolution = json.dumps({"choice": choice, "atom_id": atom_id, "detail": detail})

    # Apply the resolution
    if choice in ("confirm_a", "confirm_b") and atom_id:
        # Confirm one atom at 0.98; retract the other
        await memory.update_atom(atom_id, confidence=0.98)
        await memory.log_event(atom_id, "clarified", {"via": "review_tab", "choice": choice})
        for aid in atom_ids:
            if aid != atom_id:
                await memory.retract_atom(aid, "overridden_by_review")

    elif choice == "both_true":
        # Both coexist — mark coexist_ok in meta
        for aid in atom_ids:
            atom = await memory.get_atom(aid)
            if atom:
                meta = atom.get("meta") or {}
                meta["coexist_ok"] = True
                await memory.update_atom(aid, meta=meta)

    elif choice == "neither":
        for aid in atom_ids:
            await memory.retract_atom(aid, "user_rejected_both")

    elif choice == "dismiss":
        pass  # just close the question, no atom changes

    await db.execute(
        "UPDATE memory_question SET status=?, resolved_at=?, resolution=? WHERE id=?",
        ("resolved" if choice != "dismiss" else "dismissed", ts, resolution, question_id),
    )
    return True


async def get_eligible_clarification(session_id: str | None) -> dict | None:
    """Return the first eligible open question for inline clarification.

    Fires only when: functional kind, high-importance predicate, and no prior
    inline clarification in this session (managed by caller via seen_session set).
    """
    rows = await db.fetchall(
        "SELECT q.* FROM memory_question q WHERE q.status='open' AND q.kind='conflict' "
        "ORDER BY q.created_at ASC LIMIT 10"
    )
    for row in rows:
        atom_ids = json.loads(row.get("atom_ids") or "[]")
        for aid in atom_ids:
            atom = await memory.get_atom(aid)
            if atom and atom.get("predicate") in HIGH_IMPORTANCE_PREDICATES:
                conf = atom.get("confidence") or 0.0
                if conf >= 0.7:
                    return dict(row)
    return None
