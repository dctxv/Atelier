"""Memory CRUD + retrieval + Living Memory v2 API (M0-M8).

Response shapes stay backward-compatible with the existing frontend.
"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, HTTPException, Request

from services import config, db, memory, questions, retrieval, strands

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
async def get_timeline(
    subject: str = "user",
    predicate: str | None = None,
    strand: str | None = None,
):
    """Walk version chains for a subject+predicate or an entire strand.

    ?strand=<id>  — merge all chains belonging to the strand into one response.
    ?subject=&predicate=  — walk a single chain (existing behaviour).
    ?subject=              — list all predicates for a subject.
    """
    if strand:
        # P1.1: Strand timeline — gather all (subject, predicate) chains for the strand
        registry = await strands.load_registry()
        if not registry:
            from services.strands import _STATIC_BUNDLES
            registry = _STATIC_BUNDLES
        strand_def = next((s for s in registry if s["id"] == strand), None)
        if not strand_def:
            raise HTTPException(404, "Strand not found")

        predicates_in_strand = strand_def.get("predicates", [])
        subjects_in_strand = strand_def.get("subjects", [])

        # Build chains for all predicates (across all subjects)
        chains: dict = {}
        for pred in predicates_in_strand:
            # Find all distinct subjects with this predicate
            subj_rows = await db.fetchall(
                "SELECT DISTINCT subject FROM memory_atom "
                "WHERE predicate=? AND subject IS NOT NULL",
                (pred,),
            )
            for sr in subj_rows:
                s = sr["subject"]
                chain = await _build_chain(s, pred)
                if chain:
                    key = f"{s}:{pred}"
                    chains[key] = chain

        # Also chains for explicit subjects
        for subj in subjects_in_strand:
            pred_rows = await db.fetchall(
                "SELECT DISTINCT predicate FROM memory_atom "
                "WHERE subject=? AND predicate IS NOT NULL",
                (subj,),
            )
            for pr in pred_rows:
                pred_val = pr["predicate"]
                key = f"{subj}:{pred_val}"
                if key not in chains:
                    chain = await _build_chain(subj, pred_val)
                    if chain:
                        chains[key] = chain

        # Compute span
        all_atoms = [a for chain in chains.values() for a in chain]
        span_from = min((a.get("valid_from") or a.get("created_at") or 0) for a in all_atoms) if all_atoms else 0
        span_to = max((a.get("valid_from") or a.get("created_at") or 0) for a in all_atoms) if all_atoms else 0
        return {
            "strand": strand,
            "name": strand_def.get("name", strand),
            "chains": chains,
            "span": {"from": span_from, "to": span_to},
        }

    if not predicate:
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


# ── Strands (P1.0/P1.1) ──────────────────────────────────────────────────────

@router.get("/memory/strands")
async def get_strands():
    """List all strands with membership counts."""
    registry = await strands.load_registry()
    result = []
    for s in registry:
        atom_count = len(await strands.atoms_for_strand(s["id"]))
        result.append({
            "id": s["id"],
            "name": s["name"],
            "kind": s.get("kind", "static"),
            "predicates": s.get("predicates", []),
            "subjects": s.get("subjects", []),
            "atom_count": atom_count,
        })
    # Also an unstranded count
    all_active = await db.fetchall(
        "SELECT id, predicate, subject FROM memory_atom "
        "WHERE (status='active' OR status IS NULL) AND predicate != 'suppressed'"
    )
    stranded_ids: set[str] = set()
    for s in registry:
        for a in await strands.atoms_for_strand(s["id"]):
            stranded_ids.add(a["id"])
    unstranded_count = sum(1 for r in all_active if r["id"] not in stranded_ids)
    return {"strands": result, "unstranded_count": unstranded_count}


@router.patch("/memory/strands/{strand_id}")
async def update_strand(strand_id: str, request: Request):
    """Rename a strand (user-editable name)."""
    data = await request.json()
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Name required")
    registry = await strands.load_registry()
    for s in registry:
        if s["id"] == strand_id:
            s["name"] = name
            await strands.save_registry(registry)
            return {"ok": True}
    raise HTTPException(404, "Strand not found")


# ── Inferred knowledge dashboard (P1.5) ──────────────────────────────────────

@router.get("/memory/inferred")
async def get_inferred():
    """Return open hypotheses, inferred facts, drift observations, and scoreboard."""
    # Open hypotheses
    hyp_rows = await db.fetchall(
        "SELECT * FROM memory_atom WHERE modality='hypothesis' "
        "AND (status='active' OR status IS NULL) ORDER BY created_at DESC LIMIT 50"
    )
    hypotheses = []
    for r in hyp_rows:
        a = memory._row_to_atom(r)
        meta = a.get("meta") or {}
        # Horizon countdown in days
        horizon = meta.get("horizon")
        days_left = max(0, (horizon - db.now()) // 86400) if horizon else None
        hypotheses.append({
            **_legacy(a),
            "expected_evidence": meta.get("expected_evidence", ""),
            "disconfirming_evidence": meta.get("disconfirming_evidence", ""),
            "domain": meta.get("domain", ""),
            "generation_pattern": meta.get("generation_pattern", ""),
            "prior": meta.get("prior", 0.5),
            "days_left": days_left,
            "observations": meta.get("observations", []),
            "watched": meta.get("watched", False),
        })

    # Inferred facts (modality=insight with inferred_from_hypothesis provenance)
    insight_rows = await db.fetchall(
        "SELECT * FROM memory_atom WHERE modality='insight' "
        "AND (status='active' OR status IS NULL) ORDER BY created_at DESC LIMIT 50"
    )
    inferred_facts = []
    for r in insight_rows:
        a = memory._row_to_atom(r)
        meta = a.get("meta") or {}
        inferred_facts.append({
            **_legacy(a),
            "inferred_from_hypothesis": meta.get("inferred_from_hypothesis"),
            "confirmed_by_atom": meta.get("confirmed_by_atom"),
            "kind": meta.get("kind", "inferred"),
        })

    # Scoreboard from calibration blob
    calib_raw = await config.get_setting("memory.calibration")
    scoreboard: dict = {}
    if calib_raw:
        try:
            calib = json.loads(calib_raw)
            patterns_data = calib.get("hypothesis_patterns", {})
            for pattern, data in patterns_data.items():
                c = data.get("confirmed", 0)
                r = data.get("refuted", 0)
                total = c + r
                precision = c / total if total > 0 else None
                from workers.memory_prescient import _rolling_precision
                outcomes = data.get("outcomes", [])
                rolling = _rolling_precision(outcomes) if outcomes else None
                floor_raw = await config.get_setting("memory.hyp_flaw_precision_floor")
                floor = float(floor_raw) if floor_raw else 0.40
                scoreboard[pattern] = {
                    "confirmed": c, "refuted": r,
                    "precision": rolling,
                    "suppressed": rolling is not None and rolling < floor,
                }
        except Exception:
            pass

    return {
        "hypotheses": hypotheses,
        "inferred_facts": inferred_facts,
        "scoreboard": scoreboard,
    }


@router.post("/memory/inferred/{atom_id}/confirm")
async def confirm_inferred(atom_id: str):
    """Confirm a hypothesis or inferred atom → promote to ordinary 0.98 fact."""
    atom = await memory.get_atom(atom_id)
    if not atom:
        raise HTTPException(404, "Atom not found")
    await memory.update_atom(atom_id, confidence=0.98)
    # Flip modality to factual so the (inferred) tag is removed
    await db.execute(
        "UPDATE memory_atom SET modality='factual' WHERE id=?", (atom_id,)
    )
    await db.bump_mutation_seq()
    await memory.log_event(atom_id, "clarified", {"via": "inferred_confirm"})
    return {"ok": True}


@router.post("/memory/inferred/{atom_id}/reject")
async def reject_inferred(atom_id: str):
    """Reject a hypothesis or inferred atom → retract + update ledger."""
    atom = await memory.get_atom(atom_id)
    if not atom:
        raise HTTPException(404, "Atom not found")
    meta = atom.get("meta") or {}
    pattern = meta.get("generation_pattern", "extrapolation")
    if atom.get("modality") == "hypothesis":
        # Run through refutation path
        from workers.memory_prescient import _update_flaw_ledger
        await _update_flaw_ledger(pattern, "r")
    await memory.retract_atom(atom_id, "user_rejected")
    return {"ok": True}


@router.post("/memory/inferred/{atom_id}/watch")
async def watch_inferred(atom_id: str):
    """Mark a hypothesis as 'watching' — no-op on atoms, just sets meta flag."""
    atom = await memory.get_atom(atom_id)
    if not atom:
        raise HTTPException(404, "Atom not found")
    meta = atom.get("meta") or {}
    meta["watched"] = True
    await memory.update_atom(atom_id, meta=meta)
    return {"ok": True}


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
