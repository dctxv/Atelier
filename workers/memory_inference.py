"""W2 — inferential ("Claude-level") memory.

A corpus-level inference pass that reasons ACROSS the atom corpus over time —
not the single-message, literal extraction in workers/extraction.py, and not the
future-prediction hypotheses in workers/memory_prescient.py. It detects:

  - behavioural patterns      (recurring actions / rhythms across sessions)
  - implied preferences       (things consistently implied but never stated)
  - temporal evolution        (beliefs/goals that have shifted — flag, don't overwrite)
  - contradictions            (conflicting atoms — surface for reconciliation)

Strictly background (never the hot path). Every produced inference is a *derived*
atom (services/memory.add_inference): modality='insight', status='proposed', with
provenance links to the source atoms. It is INVISIBLE to retrieval until the user
confirms it (Visibility Law). Re-running is idempotent — add_inference dedups
against existing inferences.

All thresholds are [VALIDATE] config knobs (app_config keys below).
"""
from __future__ import annotations

import datetime
import json

from services import config, db, llm, memory
from . import jobs

# ── Config defaults (all [VALIDATE]) ──────────────────────────────────────────
_DEFAULTS = {
    "memory.inference_enabled":      True,
    "memory.inference_max_atoms":    200,   # corpus sample size per pass
    "memory.inference_min_evidence": 2,     # min source atoms to form an inference
    "memory.inference_max_new":      12,    # cap new inferences per pass
    "memory.inference_cadence_h":    24,    # how often the pass runs
}


async def _cfg(key: str):
    val = await config.get_setting(key)
    default = _DEFAULTS[key]
    if val is None:
        return default
    if isinstance(default, bool):
        return str(val).lower() in ("1", "true", "yes")
    if isinstance(default, int):
        try:
            return int(val)
        except (ValueError, TypeError):
            return default
    return val


_INFER_SYSTEM = '''\
You reason ACROSS a user's memory corpus to infer things that were implied but
never stated outright. You are shown numbered stated facts about the user. Find
durable, non-obvious inferences SUPPORTED BY MULTIPLE facts. Do NOT restate a
single fact. Do NOT invent anything a fact does not support.

Return ONLY a JSON array (no prose, no code fences). Each item:
{
  "kind": "pattern" | "implied_preference" | "evolution" | "contradiction",
  "text": "<one concise third-person inference, e.g. 'Clay tends to work late at night'>",
  "subject": "<entity, lowercase; 'user' for the user>",
  "predicate": "<short relationship, lowercase>",
  "object": "<value or null>",
  "evidence": [<indices of the supporting facts, 2+ for non-contradictions>],
  "confidence": <0.0-1.0, your certainty in the inference>
}

Rules:
- kind=pattern: a recurring behaviour/rhythm across several facts.
- kind=implied_preference: a preference consistently implied, never directly said.
- kind=evolution: a belief/goal that has CHANGED over time (cite the before+after
  facts as evidence). Flag the change; never claim the old one is simply false.
- kind=contradiction: two+ facts that genuinely conflict. evidence = the
  conflicting indices. Describe the conflict in text. Do NOT pick a winner.
- Every non-contradiction inference needs evidence from >= 2 distinct facts.
- Prefer fewer, well-supported inferences over many weak ones. If nothing is
  well-supported, return [].
'''


def _parse_json_array(raw: str) -> list:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        return json.loads(raw[start:end + 1])
    except Exception:
        return []


def _digest(atoms: list[dict]) -> str:
    """Compact, stably-indexed corpus view for the model."""
    lines = []
    for i, a in enumerate(atoms):
        when = ""
        ts = a.get("created_at")
        if ts:
            try:
                when = datetime.datetime.fromtimestamp(ts).strftime(" [%Y-%m]")
            except Exception:
                when = ""
        lines.append(f"{i}.{when} {a['text']}")
    return "\n".join(lines)


@jobs.register("infer_memory")
async def infer_memory(payload: dict | None = None):
    if not await _cfg("memory.inference_enabled"):
        return
    # Same gate as extraction: only run when memory is on.
    if str(await config.get_setting("memory.tier_selected") or "").lower() != "true":
        return

    max_atoms    = await _cfg("memory.inference_max_atoms")
    min_evidence = await _cfg("memory.inference_min_evidence")
    max_new      = await _cfg("memory.inference_max_new")

    # Corpus = stated facts only (exclude existing inferences + hypotheses).
    rows = await db.fetchall(
        "SELECT * FROM memory_atom "
        "WHERE (status='active' OR status IS NULL) "
        "AND (modality IS NULL OR modality NOT IN ('insight','hypothesis')) "
        "ORDER BY salience DESC, created_at DESC LIMIT ?",
        (max_atoms,),
    )
    atoms = [memory._row_to_atom(r) for r in rows]
    if len(atoms) < max(3, min_evidence):
        return

    try:
        raw = await llm.cheap(
            [{"role": "system", "content": _INFER_SYSTEM},
             {"role": "user", "content": _digest(atoms)}],
            temperature=0.2,
            max_tokens=900,
            task="memory_inference",
        )
    except Exception:
        return  # no model available — pass simply doesn't run this cycle

    items = _parse_json_array(raw)
    created = 0
    for item in items:
        if created >= max_new or not isinstance(item, dict):
            break
        kind = (item.get("kind") or "pattern").strip().lower()
        text = (item.get("text") or "").strip()
        evidence = item.get("evidence") or []
        if not text or not isinstance(evidence, list):
            continue
        # Map evidence indices → source atom ids (bounds-checked).
        src_ids = [atoms[i]["id"] for i in evidence
                   if isinstance(i, int) and 0 <= i < len(atoms)]

        if kind == "contradiction":
            if len(src_ids) >= 2:
                qid = await memory.surface_contradiction(src_ids, text)
                if qid:
                    created += 1
            continue

        if len(src_ids) < min_evidence:
            continue  # not enough independent support
        try:
            conf = float(item.get("confidence"))
        except (TypeError, ValueError):
            conf = None
        atom = await memory.add_inference(
            text=text,
            source_atom_ids=src_ids,
            kind=kind,
            subject=item.get("subject"),
            predicate=item.get("predicate"),
            object_val=item.get("object"),
            confidence=conf,
        )
        if atom:
            created += 1


def register_schedule():
    """Register the periodic corpus inference pass."""
    # Cadence is read from config at enqueue time inside the job; the scheduler
    # interval here is a conservative default (re-read on restart).
    hours = _DEFAULTS["memory.inference_cadence_h"]
    jobs.add_periodic(
        lambda: jobs.enqueue("infer_memory"),
        seconds=hours * 3600,
        job_id="infer_memory",
    )
