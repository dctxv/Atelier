"""Living Memory System — Tier 3 prescient background jobs (M7).

These are long-running periodic jobs that run against the full memory substrate
to produce insights, test hypotheses, and detect staleness. They must:
  - Never block the hot path
  - Use the single SQLite writer for all mutations
  - Stay within model cost limits (drift: weekly, hypotheses: weekly)
  - Never inject hypothesis/insight atoms into chat context
"""
from __future__ import annotations

import json
import uuid

from services import db, llm, memory, config
from . import jobs


async def _get_cfg(key: str, default):
    val = await config.get_setting(key)
    if val is None:
        return default
    try:
        return type(default)(val)
    except Exception:
        return default


# ── Hypothesis engine (weekly) ────────────────────────────────────────────────

@jobs.register("memory_hypotheses")
async def generate_hypotheses(payload: dict | None = None):
    """Generate up to 3 silent, falsifiable predictions about the user's future.

    Hypotheses are stored as modality=hypothesis atoms but are NEVER injected
    into chat context. They live only in the Review surface's hypotheses sub-tab
    and feed the calibration loop.
    """
    max_open = await _get_cfg("memory.hypotheses_max_open", 15)
    per_week = await _get_cfg("memory.hypotheses_per_week", 3)
    horizon_max = await _get_cfg("memory.hypothesis_horizon_max_days", 120)

    # Count open hypotheses
    open_hyps = await db.fetchall(
        "SELECT id FROM memory_atom WHERE modality='hypothesis' AND (status='active' OR status IS NULL)"
    )
    if len(open_hyps) >= max_open:
        return  # at cap

    # Gather active atoms for context (skip hypotheses and insights)
    rows = await db.fetchall(
        "SELECT text, predicate, predicate_category, modality, confidence, created_at "
        "FROM memory_atom WHERE (status='active' OR status IS NULL) "
        "AND modality NOT IN ('hypothesis','insight') "
        "ORDER BY created_at DESC LIMIT 200"
    )
    if len(rows) < 10:
        return  # not enough data to hypothesize meaningfully

    # Build compact context
    lines = [f"- [{r['modality'] or 'fact'}] {r['text']}" for r in rows[:100]]
    context = "\n".join(lines)

    prompt = (
        "You are a silent memory analyst. Based on the user's known facts and goals below, "
        f"generate up to {min(per_week, max_open - len(open_hyps))} SHORT, falsifiable predictions "
        "about the user's near future (within 120 days). "
        "Format as JSON array, each item: "
        '{"prediction":"<text>","expected_evidence":"<what fact would confirm this>","domain":"<predicate category>"}\n\n'
        f"{context}"
    )

    try:
        raw = await llm.cheap(
            [{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=600,
        )
    except Exception:
        return

    # Parse predictions
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    start, end = raw.find("["), raw.rfind("]")
    if start == -1:
        return

    try:
        preds = json.loads(raw[start:end + 1])
    except Exception:
        return

    import datetime
    horizon = int(datetime.datetime.utcnow().timestamp()) + horizon_max * 86400

    for pred in preds[:per_week]:
        if not isinstance(pred, dict) or not pred.get("prediction"):
            continue
        meta = {
            "expected_evidence": pred.get("expected_evidence", ""),
            "horizon": horizon,
            "domain": pred.get("domain", ""),
        }
        await memory.add_atom(
            text=pred["prediction"],
            type_="fact",
            source_kind="system",
            modality="hypothesis",
            confidence=0.5,
            meta=meta,
        )


# ── Hypothesis testing (runs during consolidation) ────────────────────────────

async def test_hypotheses_against_atom(new_atom: dict) -> None:
    """Check if a newly inserted fact confirms or refutes any open hypotheses."""
    open_hyps = await db.fetchall(
        "SELECT * FROM memory_atom WHERE modality='hypothesis' AND (status='active' OR status IS NULL)"
    )
    if not open_hyps:
        return

    new_text = new_atom.get("text", "")
    if not new_text:
        return

    from services import embeddings
    new_vec = await embeddings.embed(new_text)

    for hyp in open_hyps:
        meta = json.loads(hyp.get("meta") or "{}")
        expected = meta.get("expected_evidence", "")
        horizon = meta.get("horizon")

        # Check expiry
        if horizon and db.now() > horizon:
            await db.execute(
                "UPDATE memory_atom SET status='archived' WHERE id=?", (hyp["id"],)
            )
            await memory.log_event(hyp["id"], "hypothesis_refuted",
                                   {"detail": "expired", "expired": True})
            await db.bump_mutation_seq()
            continue

        if not expected:
            continue

        # Cheap cosine check against expected evidence
        exp_vec = await embeddings.embed(expected)
        import numpy as np
        a = np.array(new_vec, dtype=np.float32)
        b = np.array(exp_vec, dtype=np.float32)
        na = np.linalg.norm(a)
        nb = np.linalg.norm(b)
        if na > 0 and nb > 0:
            cos = float(np.dot(a / na, b / nb))
        else:
            cos = 0.0

        if cos >= 0.5:
            # Mark confirmed
            await memory.log_event(hyp["id"], "hypothesis_confirmed",
                                   {"confirmed_by": new_atom.get("id"), "cos": cos})
            # Convert to insight (available for retrieval)
            await db.execute(
                "UPDATE memory_atom SET modality='insight' WHERE id=?", (hyp["id"],)
            )
            await db.bump_mutation_seq()


# ── Identity drift analysis (quarterly) ──────────────────────────────────────

@jobs.register("memory_drift")
async def analyze_drift(payload: dict | None = None):
    """Quarterly job: detect identity/attribute drift from supersession chains.

    Produces at most 3 drift observations as modality=insight atoms.
    These are NEVER injected into chat context — visible only in the
    Memory surface Insights panel.
    """
    # Gather attribute/self_perception supersession events from the past year
    cutoff = db.now() - 365 * 86400
    events = await db.fetchall(
        "SELECT e.*, a.text, a.predicate FROM memory_event e "
        "JOIN memory_atom a ON a.id = e.atom_id "
        "WHERE e.kind='superseded' AND e.created_at > ? "
        "AND a.predicate_category IN ('attribute','self_perception') "
        "ORDER BY e.created_at DESC LIMIT 100",
        (cutoff,),
    )
    if len(events) < 3:
        return  # not enough change history

    # Build a compact summary for the model
    change_lines = []
    for e in events[:50]:
        detail = json.loads(e.get("detail") or "{}")
        successor_id = detail.get("superseded_by")
        if successor_id:
            succ = await memory.get_atom(successor_id)
            if succ:
                change_lines.append(f"Changed: {e['text']} → {succ['text']}")

    if not change_lines:
        return

    context = "\n".join(change_lines[:30])

    prompt = (
        "You are a memory analyst. Based on changes to this person's self-reported traits "
        "and attributes over the past year, write up to 3 concise drift observations. "
        "Each observation should cite specific changes. "
        "Format as JSON array: "
        '[{"observation":"<text>","evidence_ids":["<atom_id1>","<atom_id2>"]}]\n\n'
        f"{context}"
    )

    try:
        raw = await llm.cheap(
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500,
        )
    except Exception:
        return

    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    start, end = raw.find("["), raw.rfind("]")
    if start == -1:
        return

    try:
        observations = json.loads(raw[start:end + 1])
    except Exception:
        return

    for obs in observations[:3]:
        if not isinstance(obs, dict) or not obs.get("observation"):
            continue
        meta = {"evidence": obs.get("evidence_ids", [])}
        await memory.add_atom(
            text=obs["observation"],
            type_="fact",
            source_kind="system",
            modality="insight",
            confidence=0.7,
            meta=meta,
        )


# ── Goal staleness check ──────────────────────────────────────────────────────

@jobs.register("memory_goal_stale")
async def check_stale_goals(payload: dict | None = None):
    """Open a register question for plans/desires untouched for 90 days."""
    stale_days = await _get_cfg("memory.goal_stale_days", 90)
    cutoff = db.now() - stale_days * 86400

    stale_goals = await db.fetchall(
        "SELECT * FROM memory_atom "
        "WHERE modality IN ('desire','plan') "
        "AND (status='active' OR status IS NULL) "
        "AND (last_used_at IS NULL OR last_used_at < ?) "
        "LIMIT 10",
        (cutoff,),
    )

    from services import questions as q_svc

    for goal in stale_goals:
        # Don't re-open if a question for this atom is already open
        existing = await db.fetchall(
            "SELECT id FROM memory_question WHERE status='open' AND atom_ids LIKE ?",
            (f'%{goal["id"]}%',),
        )
        if existing:
            continue

        prompt = (
            f"Still planning to: \"{goal['text'][:100]}\"? "
            f"(Last updated {(db.now() - (goal.get('last_used_at') or goal['created_at'])) // 86400} days ago)"
        )
        await q_svc.open_question("goal_check", [goal["id"]], prompt)


def register_schedule():
    """Register Tier 3 periodic jobs."""
    # Hypothesis generation: weekly
    jobs.add_periodic(
        lambda: jobs.enqueue("memory_hypotheses"),
        seconds=7 * 86400,
        job_id="memory_hypotheses",
    )
    # Drift analysis: quarterly (every 90 days)
    jobs.add_periodic(
        lambda: jobs.enqueue("memory_drift"),
        seconds=90 * 86400,
        job_id="memory_drift",
    )
    # Stale goal check: weekly
    jobs.add_periodic(
        lambda: jobs.enqueue("memory_goal_stale"),
        seconds=7 * 86400,
        job_id="memory_goal_stale",
    )
