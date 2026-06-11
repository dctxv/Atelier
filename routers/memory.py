"""Memory CRUD + retrieval + Living Memory v2 API (M0-M8).

Response shapes stay backward-compatible with the existing frontend.
"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, HTTPException, Request

from services import config, db, memory, questions, retrieval

router = APIRouter(prefix="/api")


def _legacy(atom: dict) -> dict:
    """Backward-compatible response shape for the existing frontend."""
    return {
        "id":         atom["id"],
        "text":       atom["text"],
        "category":   atom.get("type", "fact"),
        "timestamp":  atom.get("created_at"),
        "pinned":     bool(atom.get("pinned")),
        "source_kind": atom.get("source_kind"),
        # v2 structured fields (null on legacy atoms)
        "subject":            atom.get("subject"),
        "predicate":          atom.get("predicate"),
        "predicate_category": atom.get("predicate_category"),
        "object":             atom.get("object"),
        "polarity":           atom.get("polarity"),
        "intensity":          atom.get("intensity"),
        "modality":           atom.get("modality"),
        "confidence":         atom.get("confidence"),
        "status":             atom.get("status") or "active",
        "valid_from":         atom.get("valid_from"),
        "valid_until":        atom.get("valid_until"),
    }


# ── Tier selection (memory setup) ─────────────────────────────────────────────

@router.get("/memory/tier")
async def get_memory_tier():
    raw = await config.get_setting("memory.tier_selected", "false")
    tier_selected = str(raw or "false").lower() == "true"
    depth = await config.get_setting("memory.depth", "basic") or "basic"
    return {"tier_selected": tier_selected, "depth": depth}


@router.post("/memory/tier")
async def set_memory_tier(request: Request):
    data = await request.json()
    depth = data.get("depth", "basic")
    if depth not in ("basic", "reflective", "prescient"):
        raise HTTPException(400, "depth must be basic, reflective, or prescient")
    await config.set_setting("memory.tier_selected", "true")
    await config.set_setting("memory.depth", depth)
    return {"ok": True, "depth": depth}


# ── Memory CRUD ───────────────────────────────────────────────────────────────

@router.get("/memory")
async def get_memory():
    atoms = await memory.list_atoms()
    return {"memories": [_legacy(a) for a in atoms]}


@router.post("/memory")
async def add_memory(request: Request):
    data = await request.json()
    text = (data.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "Memory text required")
    atom = await memory.add_atom(
        text=text,
        type_=data.get("category", "fact"),
        source_kind="manual",
        pinned=bool(data.get("pinned", False)),
        subject=data.get("subject"),
        predicate=data.get("predicate"),
        predicate_category=data.get("predicate_category"),
        object_val=data.get("object"),
        confidence=data.get("confidence"),
        modality=data.get("modality"),
    )
    return {"ok": True, "memory": _legacy(atom)}


@router.put("/memory/{memory_id}")
async def update_memory(memory_id: str, request: Request):
    data = await request.json()
    atom = await memory.update_atom(
        memory_id,
        text=data.get("text"),
        type_=data.get("category"),
        pinned=data.get("pinned"),
        confidence=data.get("confidence"),
        status=data.get("status"),
        valid_until=data.get("valid_until"),
    )
    if not atom:
        raise HTTPException(404, "Memory not found")
    return {"ok": True, "memory": _legacy(atom)}


@router.delete("/memory/{memory_id}")
async def delete_memory(memory_id: str):
    if not await memory.delete_atom(memory_id):
        raise HTTPException(404, "Memory not found")
    return {"ok": True}


@router.post("/memory/{memory_id}/forget")
async def forget_memory(memory_id: str):
    """Hard delete — removes atom, vector, FTS, and events."""
    if not await memory.delete_atom(memory_id):
        raise HTTPException(404, "Memory not found")
    # Also delete events for this atom
    await db.execute("DELETE FROM memory_event WHERE atom_id=?", (memory_id,))
    return {"ok": True}


@router.post("/memory/{memory_id}/retract")
async def retract_memory(memory_id: str, request: Request):
    """Soft retract — confidence=0, status=retracted, audit trail kept."""
    data = await request.json()
    reason = data.get("reason", "user")
    if not await memory.retract_atom(memory_id, reason):
        raise HTTPException(404, "Memory not found")
    return {"ok": True}


@router.post("/memory/{memory_id}/pin")
async def pin_memory(memory_id: str, request: Request):
    data = await request.json()
    pinned = bool(data.get("pinned", True))
    if not await memory.set_pinned(memory_id, pinned):
        raise HTTPException(404, "Memory not found")
    return {"ok": True, "pinned": pinned}


@router.post("/memory/search")
async def search_memory(request: Request):
    data = await request.json()
    as_of_val = data.get("as_of")
    atoms = await retrieval.retrieve(
        (data.get("query") or "").strip(),
        k=int(data.get("k", 12)),
        budget_tokens=int(data.get("budget_tokens", 700)),
        include_faded=bool(data.get("include_faded", False)),
        as_of=int(as_of_val) if as_of_val else None,
    )
    return {"results": atoms}


# ── Questions / Review tab (M4) ───────────────────────────────────────────────

@router.get("/memory/questions")
async def get_questions():
    """List open questions for the Review tab."""
    open_qs    = await questions.list_questions("open")
    resolved_qs = await questions.list_questions("resolved")
    dismissed_qs = await questions.list_questions("dismissed")
    return {
        "open":     open_qs,
        "resolved": resolved_qs[:20],  # cap for UI
        "dismissed": dismissed_qs[:20],
    }


@router.post("/memory/questions/{question_id}/resolve")
async def resolve_question(question_id: str, request: Request):
    data = await request.json()
    choice   = data.get("choice", "dismiss")
    atom_id  = data.get("atom_id")
    detail   = data.get("detail")
    ok = await questions.resolve_question(question_id, choice, atom_id, detail)
    if not ok:
        raise HTTPException(404, "Question not found or already resolved")
    return {"ok": True}


# ── Timeline endpoint (M6) ────────────────────────────────────────────────────

@router.get("/memory/timeline")
async def get_timeline(subject: str = "user", predicate: str | None = None):
    """Walk the supersession chain for a given subject+predicate bundle.

    Returns ordered list of atoms forming the version history.
    """
    if not predicate:
        # Return all predicates for this subject, grouped
        rows = await db.fetchall(
            "SELECT DISTINCT predicate FROM memory_atom "
            "WHERE subject=? AND predicate IS NOT NULL ORDER BY predicate",
            (subject,),
        )
        predicates = [r["predicate"] for r in rows]
        result = {}
        for pred in predicates:
            chain = await _build_chain(subject, pred)
            if chain:
                result[pred] = chain
        return {"subject": subject, "predicates": result}
    else:
        chain = await _build_chain(subject, predicate)
        return {"subject": subject, "predicate": predicate, "chain": chain}


async def _build_chain(subject: str, predicate: str) -> list[dict]:
    """Build ordered version chain for subject+predicate."""
    rows = await db.fetchall(
        "SELECT * FROM memory_atom WHERE subject=? AND predicate=? ORDER BY valid_from ASC",
        (subject, predicate),
    )
    if not rows:
        return []

    result = []
    for r in rows:
        atom = memory._row_to_atom(r)
        # Fetch events for this atom
        events = await db.fetchall(
            "SELECT kind, created_at, detail FROM memory_event WHERE atom_id=? ORDER BY created_at",
            (r["id"],),
        )
        atom["events"] = [
            {
                "kind": e["kind"],
                "created_at": e["created_at"],
                "detail": json.loads(e["detail"]) if e["detail"] else None,
            }
            for e in events
        ]
        result.append(atom)

    return result


# ── Goals / aspirations view (M7) ─────────────────────────────────────────────

@router.get("/memory/goals")
async def get_goals():
    """Return active desire and plan atoms (goal ledger)."""
    rows = await db.fetchall(
        "SELECT * FROM memory_atom WHERE modality IN ('desire','plan') "
        "AND (status='active' OR status IS NULL) ORDER BY created_at DESC LIMIT 100"
    )
    atoms = [memory._row_to_atom(r) for r in rows]
    return {"goals": [_legacy(a) for a in atoms]}


@router.post("/memory/goals/{atom_id}/close")
async def close_goal(atom_id: str, request: Request):
    """Mark a goal as achieved or dropped."""
    data = await request.json()
    outcome = data.get("outcome", "achieved")  # achieved | dropped

    atom = await memory.get_atom(atom_id)
    if not atom:
        raise HTTPException(404, "Atom not found")

    meta = atom.get("meta") or {}
    meta["goal_outcome"] = outcome
    await memory.update_atom(
        atom_id,
        status="archived",
        valid_until=db.now(),
        meta=meta,
    )
    await memory.log_event(atom_id, "goal_progress", {"outcome": outcome})
    return {"ok": True}


# ── Hypothesis engine view (M7) ───────────────────────────────────────────────

@router.get("/memory/hypotheses")
async def get_hypotheses():
    """Return open hypothesis atoms (never appear in chat context)."""
    rows = await db.fetchall(
        "SELECT * FROM memory_atom WHERE modality='hypothesis' "
        "AND (status='active' OR status IS NULL) ORDER BY created_at DESC LIMIT 50"
    )
    atoms = [memory._row_to_atom(r) for r in rows]
    return {"hypotheses": [_legacy(a) for a in atoms]}


# ── Events / audit trail ──────────────────────────────────────────────────────

@router.get("/memory/{memory_id}/events")
async def get_atom_events(memory_id: str):
    atom = await memory.get_atom(memory_id)
    if not atom:
        raise HTTPException(404, "Memory not found")
    events = await db.fetchall(
        "SELECT * FROM memory_event WHERE atom_id=? ORDER BY created_at DESC",
        (memory_id,),
    )
    return {
        "atom": _legacy(atom),
        "events": [
            {
                "id": e["id"],
                "kind": e["kind"],
                "detail": json.loads(e["detail"]) if e["detail"] else None,
                "created_at": e["created_at"],
            }
            for e in events
        ],
    }


# ── Export (M8) ───────────────────────────────────────────────────────────────

@router.get("/memory/export")
async def export_memory():
    """Export complete memory state as structured JSON."""
    atoms = await memory.list_atoms(limit=100_000, include_inactive=True)
    events = await db.fetchall(
        "SELECT * FROM memory_event ORDER BY created_at DESC LIMIT 10000"
    )
    open_qs = await questions.list_questions("open")
    calib = await config.get_setting("memory.calibration")

    return {
        "atoms": atoms,
        "events": [
            {
                "id": e["id"],
                "atom_id": e["atom_id"],
                "kind": e["kind"],
                "detail": json.loads(e["detail"]) if e["detail"] else None,
                "created_at": e["created_at"],
            }
            for e in events
        ],
        "open_questions": open_qs,
        "calibration": json.loads(calib) if calib else None,
        "exported_at": db.now(),
    }


# ── Artistry / narrative (M8) ─────────────────────────────────────────────────

@router.post("/memory/story")
async def memory_story(request: Request):
    """Generate a narrative from memory. Uses the active (best-quality) model."""
    data = await request.json()
    topic    = data.get("topic") or ""
    subject  = data.get("subject") or "user"
    timeframe = data.get("timeframe")

    # Gather relevant atoms
    query = topic or f"about {subject}"
    if timeframe:
        query = f"{query} {timeframe}"
    atoms = await retrieval.retrieve(query, k=30, budget_tokens=3000)
    if not atoms:
        return {"narrative": "No memories found for this topic.", "atom_count": 0}

    # Also get timeline data for the most common predicate
    atom_count = len([a for a in atoms if a.get("source_type") == "memory"])

    lines = ["[MEMORY ARTISTRY]"]
    lines.append(f"Topic: {topic or 'general'}")
    lines.append(f"Atoms included: {atom_count}")
    lines.append("")
    for a in atoms:
        if a.get("source_type") == "memory":
            status = a.get("status", "active")
            if status == "retracted":
                continue  # never include retracted
            ts_str = ""
            if a.get("created_at"):
                import datetime
                try:
                    ts_str = datetime.datetime.fromtimestamp(
                        a["created_at"]
                    ).strftime("%Y-%m")
                except Exception:
                    pass
            marker = "[inferred]" if a.get("modality") in ("hypothesis", "insight") else ""
            lines.append(f"- {a['text']} {marker} ({ts_str})".strip())

    memory_context = "\n".join(lines)

    prompt = (
        f"You are writing a biographical memory narrative in a literary register. "
        f"Rules: mark non-obvious inferences with [inferred]; narrate contradictions as tensions, "
        f"never silently resolve them; exclude retracted material; end with a provenance note. "
        f"\n\n{memory_context}"
    )

    try:
        from services import llm
        narrative = await llm.complete(
            [{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1500,
        )
    except Exception as e:
        narrative = f"Narrative generation unavailable: {e}"

    return {"narrative": narrative, "atom_count": atom_count}
