"""Living Memory System — Tier 3 prescient background jobs.

Phases implemented here:
  P1.3 — Negative-Space Memory (suppression atoms + weekly suppression pass)
  P1.5 — Hypothesis Engine v2 (richer records, NLI, flaw ledger, inferred facts)
  Also: identity drift analysis, goal staleness check (existing, carried over)

Two Laws govern all inference work (restated per design mandate):
1. Visibility Law: Nothing inferred enters chat context until user-confirmed
   or explicitly tagged as inference at render time.  Suppression atoms and
   hypothesis atoms never appear in retrieval results (enforced in retrieval.py).
2. Warming Law: Anticipation changes latency only, never content.

Jobs must:
  - Never block the hot path
  - Use the single SQLite writer for all mutations
  - Stay within model cost limits
  - Never inject hypothesis/insight atoms into chat context (G5f invariant)
"""
from __future__ import annotations

import json
import uuid

from services import config, db, llm, memory, questions as q_svc
from . import jobs

_GENERATION_PATTERNS = (
    "extrapolation",
    "analogy_to_past_decision",
    "goal_implication",
    "correlation_promotion",
)


async def _get_cfg(key: str, default):
    val = await config.get_setting(key)
    if val is None:
        return default
    try:
        return type(default)(val)
    except Exception:
        return default


# ── Suppression helpers (P1.3) ────────────────────────────────────────────────

async def is_suppressed(topic_key: str, threshold: float = 0.6) -> bool:
    """Return True when an active suppression atom for this topic key exists
    with confidence >= threshold.  Used by all proactive generators."""
    row = await db.fetchone(
        "SELECT confidence FROM memory_atom "
        "WHERE predicate='suppressed' AND subject=? "
        "AND (status='active' OR status IS NULL)",
        (topic_key,),
    )
    return bool(row and (row.get("confidence") or 0.0) >= threshold)


async def _upsert_suppression_atom(
    topic_key: str,
    source: str,
    source_ids: list[str],
    step: float,
    cap: float,
    max_conf: float,
) -> None:
    """Increment suppression confidence for a topic, or create if new."""
    row = await db.fetchone(
        "SELECT id, confidence, meta FROM memory_atom "
        "WHERE predicate='suppressed' AND subject=? "
        "AND (status='active' OR status IS NULL)",
        (topic_key,),
    )
    now_ts = db.now()
    if row:
        old_conf = row.get("confidence") or cap
        new_conf = min(max_conf, old_conf + step)
        try:
            meta = json.loads(row.get("meta") or "{}")
        except Exception:
            meta = {}
        meta["last_signal_ts"] = now_ts
        if source_ids:
            meta.setdefault("source_ids", [])
            meta["source_ids"] = list(set(meta["source_ids"] + source_ids))[-20:]
        await db.execute(
            "UPDATE memory_atom SET confidence=?, meta=? WHERE id=?",
            (new_conf, json.dumps(meta), row["id"]),
        )
        await db.bump_mutation_seq()
    else:
        # First signal starts at cap (0.4) + step (0.15) = 0.55
        initial_conf = min(max_conf, cap + step)
        meta = {
            "suppress": True,
            "source": source,
            "source_ids": source_ids,
            "last_signal_ts": now_ts,
        }
        await memory.add_atom(
            text=f"Suppressed topic: {topic_key}",
            type_="fact",
            source_kind="system",
            subject=topic_key,
            predicate="suppressed",
            predicate_category="experiential",  # no standard decay — handled by suppression pass
            confidence=initial_conf,
            meta=meta,
        )


def _topic_key_from_question(q: dict, atoms: list[dict]) -> str | None:
    """Extract a topic key string from a dismissed question."""
    kind = q.get("kind", "")
    if kind == "goal_check" and atoms:
        return f"goal:{atoms[0].get('text', '')[:80]}"
    if kind == "insight_offer":
        # For strand proposals, use a hash of the prompt
        import hashlib
        sig = hashlib.md5((q.get("prompt_text") or "").encode()).hexdigest()[:12]
        return f"strand_proposal:{sig}"
    if atoms:
        subj = (atoms[0].get("subject") or "").lower()
        pred = (atoms[0].get("predicate") or "").lower()
        if subj and pred:
            return f"{subj}:{pred}"
    return None


@jobs.register("memory_suppression_pass")
async def weekly_suppression_pass(payload: dict | None = None):
    """Weekly pass: learn from dismissed questions and dropped goals (P1.3).

    Creates and updates suppression atoms.  Also applies exponential decay to
    existing suppression atoms and retracts those below the floor confidence.
    """
    step = float(await _get_cfg("memory.suppress_confidence_step", 0.15))
    cap = 0.4       # floor for first signal
    max_conf = float(await _get_cfg("memory.suppress_max_confidence", 0.85))
    half_life = float(await _get_cfg("memory.suppress_half_life_days", 180))

    cutoff_7d = db.now() - 7 * 86400

    # --- Dismissed questions in the past 7 days ---
    dismissed_qs = await db.fetchall(
        "SELECT * FROM memory_question WHERE status='dismissed' AND resolved_at > ?",
        (cutoff_7d,),
    )
    for q in dismissed_qs:
        atom_ids = json.loads(q.get("atom_ids") or "[]")
        atoms = []
        for aid in atom_ids:
            a = await memory.get_atom(aid)
            if a:
                atoms.append(a)
        key = _topic_key_from_question(q, atoms)
        if not key:
            continue
        await _upsert_suppression_atom(key, f"dismissed_{q.get('kind','question')}",
                                        atom_ids, step, cap, max_conf)

    # --- Dropped goals in the past 7 days ---
    dropped_goals = await db.fetchall(
        "SELECT a.* FROM memory_atom a "
        "JOIN memory_event e ON e.atom_id = a.id "
        "WHERE e.kind='goal_progress' AND e.created_at > ? "
        "AND a.modality IN ('desire','plan')",
        (cutoff_7d,),
    )
    for g in dropped_goals:
        try:
            detail = json.loads(
                (await db.fetchone(
                    "SELECT detail FROM memory_event WHERE atom_id=? AND kind='goal_progress' "
                    "ORDER BY created_at DESC LIMIT 1",
                    (g["id"],),
                ) or {}).get("detail") or "{}"
            )
        except Exception:
            detail = {}
        if detail.get("outcome") == "dropped":
            key = f"goal:{g.get('text', '')[:80]}"
            await _upsert_suppression_atom(key, "dropped_goal", [g["id"]], step, cap, max_conf)

    # --- Decay pass on existing suppression atoms ---
    import math
    suppression_atoms = await db.fetchall(
        "SELECT id, confidence, created_at, meta FROM memory_atom "
        "WHERE predicate='suppressed' AND (status='active' OR status IS NULL)"
    )
    retract_floor = 0.4
    now_ts = db.now()
    half_life_s = half_life * 86400

    for sa in suppression_atoms:
        try:
            meta = json.loads(sa.get("meta") or "{}")
        except Exception:
            meta = {}
        last_signal = meta.get("last_signal_ts") or sa.get("created_at") or now_ts
        age_days = (now_ts - last_signal) / 86400.0
        if age_days <= 0:
            continue
        decay = math.exp(-math.log(2) * age_days * 86400 / half_life_s)
        old_conf = sa.get("confidence") or cap
        new_conf = old_conf * decay
        if new_conf < retract_floor:
            await memory.retract_atom(sa["id"], "suppression_decayed")
        else:
            await db.execute(
                "UPDATE memory_atom SET confidence=? WHERE id=?",
                (new_conf, sa["id"]),
            )
    if suppression_atoms:
        await db.bump_mutation_seq()


# ── Hypothesis engine v2 (P1.5) ──────────────────────────────────────────────

def _load_calibration(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _rolling_precision(outcomes: list[str]) -> float:
    """Precision = confirmed / (confirmed + refuted) over last 20 outcomes."""
    window = outcomes[-20:]
    c = window.count("c")
    r = window.count("r")
    total = c + r
    return c / total if total > 0 else 0.5  # default 0.5 when no data


async def _suppressed_topics_for_prompt() -> list[str]:
    """Return a list of suppressed topic keys for injection into the generation prompt."""
    rows = await db.fetchall(
        "SELECT subject FROM memory_atom "
        "WHERE predicate='suppressed' AND (status='active' OR status IS NULL) "
        "AND confidence >= 0.6 LIMIT 20"
    )
    return [r["subject"] for r in rows if r.get("subject")]


@jobs.register("memory_hypotheses")
async def generate_hypotheses(payload: dict | None = None):
    """Generate silent, falsifiable predictions with richer schema (P1.5).

    Hypotheses are stored as modality=hypothesis atoms and NEVER injected
    into chat context (G5f invariant).  Any item lacking a disconfirming_evidence
    field is dropped before storage.
    """
    max_open = await _get_cfg("memory.hypotheses_max_open", 15)
    per_week = await _get_cfg("memory.hypotheses_per_week", 3)
    horizon_max = await _get_cfg("memory.hypothesis_horizon_max_days", 120)

    open_hyps = await db.fetchall(
        "SELECT id FROM memory_atom WHERE modality='hypothesis' AND (status='active' OR status IS NULL)"
    )
    if len(open_hyps) >= max_open:
        return

    rows = await db.fetchall(
        "SELECT text, predicate, predicate_category, modality, confidence, created_at "
        "FROM memory_atom WHERE (status='active' OR status IS NULL) "
        "AND modality NOT IN ('hypothesis','insight') "
        "AND predicate != 'suppressed' "
        "ORDER BY created_at DESC LIMIT 200"
    )
    if len(rows) < 10:
        return

    # Flaw ledger — suppress unreliable patterns [VALIDATE]
    precision_floor = float(await _get_cfg("memory.hyp_flaw_precision_floor", 0.40))
    calib_raw = await config.get_setting("memory.calibration")
    calib = _load_calibration(calib_raw)
    patterns_data = calib.get("hypothesis_patterns", {})
    suppressed_patterns: list[str] = [
        p for p, d in patterns_data.items()
        if _rolling_precision(d.get("outcomes", [])) < precision_floor
    ]
    suppressed_topics = await _suppressed_topics_for_prompt()

    lines = [f"- [{r['modality'] or 'fact'}] {r['text']}" for r in rows[:100]]
    context = "\n".join(lines)

    suppression_lines = ""
    for p in suppressed_patterns:
        suppression_lines += (
            f"\n- You have historically been unreliable with {p} patterns; "
            f"do NOT generate {p}-pattern hypotheses this cycle."
        )
    if suppressed_topics:
        suppression_lines += (
            f"\n- Do NOT generate hypotheses about these suppressed topics: "
            + ", ".join(suppressed_topics[:10])
        )

    n_to_generate = min(per_week, max_open - len(open_hyps))

    prompt = (
        f"You are a silent memory analyst. Based on the user's known facts below, "
        f"generate up to {n_to_generate} SHORT, falsifiable predictions about the "
        f"user's near future (within {horizon_max} days).\n\n"
        "Rules:\n"
        "1. Every hypothesis MUST include a disconfirming_evidence field (what fact would REFUTE this). "
        "   Any item without disconfirming_evidence will be silently dropped.\n"
        "2. Use one of these generation patterns: extrapolation, analogy_to_past_decision, "
        "   goal_implication, correlation_promotion.\n"
        "3. Include a prior probability (0.0–1.0) representing your confidence this will happen.\n"
        f"{suppression_lines}\n\n"
        "Format as JSON array, each item:\n"
        '{"prediction":"<text>","expected_evidence":"<what confirms this>",'
        '"disconfirming_evidence":"<what refutes this>","domain":"<area of life>",'
        '"generation_pattern":"<one of the 4 patterns>","prior":<0.0-1.0>}\n\n'
        f"{context}"
    )

    try:
        raw = await llm.cheap(
            [{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=800,
            task="hypothesis_generation",
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
        preds = json.loads(raw[start:end + 1])
    except Exception:
        return

    import datetime
    horizon = int(datetime.datetime.utcnow().timestamp()) + horizon_max * 86400

    for pred in preds[:per_week]:
        if not isinstance(pred, dict) or not pred.get("prediction"):
            continue
        # Drop any hypothesis without a falsifier (G5 requirement)
        if not pred.get("disconfirming_evidence"):
            continue
        pattern = pred.get("generation_pattern", "extrapolation")
        if pattern not in _GENERATION_PATTERNS:
            pattern = "extrapolation"
        prior = float(pred.get("prior") or 0.5)
        prior = max(0.05, min(0.95, prior))
        meta = {
            "expected_evidence": pred.get("expected_evidence", ""),
            "disconfirming_evidence": pred.get("disconfirming_evidence", ""),
            "horizon": horizon,
            "domain": pred.get("domain", ""),
            "generation_pattern": pattern,
            "prior": prior,
            "observations": [],
        }
        await memory.add_atom(
            text=pred["prediction"],
            type_="fact",
            source_kind="system",
            modality="hypothesis",
            confidence=prior,
            meta=meta,
        )


# ── Hypothesis testing (NLI-style, P1.5) ─────────────────────────────────────

async def _nli_call(atom_text: str, evidence_text: str) -> tuple[str, float]:
    """Cheap NLI check: does atom_text support/refute/neutral the evidence_text?

    Returns (verdict, strength): verdict in {supports, refutes, neutral}.
    Falls back to neutral on error.
    """
    prompt = (
        f'Memory fact: "{atom_text}"\n'
        f'Evidence claim: "{evidence_text}"\n\n'
        "Does the memory fact supports, refutes, or is neutral toward the evidence claim?\n"
        'Reply ONLY as JSON: {"verdict": "supports|refutes|neutral", "strength": 0.0}'
    )
    try:
        raw = await llm.cheap(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=60,
            task="hypothesis_nli",
        )
        raw = (raw or "").strip()
        # Extract JSON
        s, e = raw.find("{"), raw.rfind("}")
        if s != -1 and e != -1:
            data = json.loads(raw[s:e + 1])
            verdict = data.get("verdict", "neutral").lower()
            if verdict not in ("supports", "refutes", "neutral"):
                verdict = "neutral"
            strength = float(data.get("strength", 0.5))
            strength = max(0.0, min(1.0, strength))
            return verdict, strength
    except Exception:
        pass
    return "neutral", 0.5


async def test_hypotheses_against_atom(new_atom: dict) -> None:
    """Check a newly inserted fact against all open hypotheses (P1.5 §6.2).

    Called from the extraction worker (background, never hot path).
    """
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

    import numpy as np

    cos_gate = float(await _get_cfg("memory.hyp_gate_cos", 0.50))
    confirm_strength_floor = 0.6  # [VALIDATE]

    for hyp in open_hyps:
        try:
            meta = json.loads(hyp.get("meta") or "{}")
        except Exception:
            meta = {}

        expected = meta.get("expected_evidence", "")
        disconfirm = meta.get("disconfirming_evidence", "")
        horizon = meta.get("horizon")
        pattern = meta.get("generation_pattern", "extrapolation")
        prior = float(meta.get("prior") or 0.5)

        # Horizon expiry — log as expired, NOT a flaw (running out of time ≠ reasoning error)
        if horizon and db.now() > horizon:
            await db.execute(
                "UPDATE memory_atom SET status='archived' WHERE id=?", (hyp["id"],)
            )
            await memory.log_event(hyp["id"], "hypothesis_expired", {"detail": "horizon_passed"})
            await db.bump_mutation_seq()
            continue

        # Quick cosine gate against both evidence descriptions
        a = np.array(new_vec, dtype=np.float32)
        an = np.linalg.norm(a)

        async def _cosine_to(text: str) -> float:
            if not text:
                return 0.0
            ev = await embeddings.embed(text)
            b = np.array(ev, dtype=np.float32)
            bn = np.linalg.norm(b)
            if an > 0 and bn > 0:
                return float(np.dot(a / an, b / bn))
            return 0.0

        cos_exp = await _cosine_to(expected)
        cos_dis = await _cosine_to(disconfirm)

        if max(cos_exp, cos_dis) < cos_gate:
            # Not related to this hypothesis at all
            continue

        # NLI calls
        verdict_exp, strength_exp = ("neutral", 0.5)
        verdict_dis, strength_dis = ("neutral", 0.5)

        if cos_exp >= cos_gate and expected:
            verdict_exp, strength_exp = await _nli_call(new_text, expected)
        if cos_dis >= cos_gate and disconfirm:
            verdict_dis, strength_dis = await _nli_call(new_text, disconfirm)

        # Decision logic
        confirmed = (
            verdict_exp == "supports" and strength_exp >= confirm_strength_floor
        )
        refuted = (
            (verdict_dis == "supports" and strength_dis >= confirm_strength_floor)
            or (verdict_exp == "refutes" and strength_exp >= confirm_strength_floor)
        )

        if confirmed:
            await _confirm_hypothesis(hyp, new_atom, prior, pattern)
        elif refuted:
            await _refute_hypothesis(hyp, new_atom, pattern, calib_raw=await config.get_setting("memory.calibration"))
        else:
            # Accumulate observation
            observations = meta.get("observations", [])
            observations.append({
                "atom_id": new_atom.get("id"),
                "verdict_exp": verdict_exp,
                "strength_exp": strength_exp,
                "verdict_dis": verdict_dis,
                "strength_dis": strength_dis,
                "ts": db.now(),
            })
            meta["observations"] = observations[-50:]  # cap
            await db.execute(
                "UPDATE memory_atom SET meta=? WHERE id=?",
                (json.dumps(meta), hyp["id"]),
            )


async def _confirm_hypothesis(hyp: dict, confirming_atom: dict, prior: float, pattern: str) -> None:
    """Confirmation path: mint a new inferred atom; archive the hypothesis (P1.5 §6.3)."""
    # Confidence formula: prior × 0.8 + 0.18 [VALIDATE the two constants]
    factor = float(await _get_cfg("memory.hyp_confirm_conf_factor", 0.8))
    base = float(await _get_cfg("memory.hyp_confirm_conf_base", 0.18))
    inferred_conf = max(0.1, min(0.98, prior * factor + base))

    # Mint the inferred fact
    inferred = await memory.add_atom(
        text=hyp["text"],
        type_="fact",
        source_kind="system",
        modality="insight",
        confidence=inferred_conf,
        meta={
            "inferred_from_hypothesis": hyp["id"],
            "confirmed_by_atom": confirming_atom.get("id"),
        },
    )

    # Archive the hypothesis with event
    await db.execute(
        "UPDATE memory_atom SET status='archived' WHERE id=?", (hyp["id"],)
    )
    await memory.log_event(hyp["id"], "hypothesis_confirmed", {
        "confirmed_by": confirming_atom.get("id"),
        "inferred_atom": inferred["id"] if inferred else None,
    })
    await db.bump_mutation_seq()

    # Update calibration ledger
    await _update_flaw_ledger(pattern, "c")


async def _refute_hypothesis(hyp: dict, refuting_atom: dict, pattern: str, calib_raw: str | None) -> None:
    """Refutation path: archive hypothesis; update flaw ledger (P1.5 §6.4)."""
    await db.execute(
        "UPDATE memory_atom SET status='archived' WHERE id=?", (hyp["id"],)
    )
    await memory.log_event(hyp["id"], "hypothesis_refuted", {
        "refuted_by": refuting_atom.get("id"),
    })
    await db.bump_mutation_seq()
    await _update_flaw_ledger(pattern, "r")


async def _update_flaw_ledger(pattern: str, outcome: str) -> None:
    """Append outcome ('c'=confirmed, 'r'=refuted) to rolling per-pattern ledger."""
    calib_raw = await config.get_setting("memory.calibration")
    calib = _load_calibration(calib_raw)
    patterns_data = calib.setdefault("hypothesis_patterns", {})
    p_data = patterns_data.setdefault(pattern, {"confirmed": 0, "refuted": 0, "outcomes": []})
    if outcome == "c":
        p_data["confirmed"] = p_data.get("confirmed", 0) + 1
    else:
        p_data["refuted"] = p_data.get("refuted", 0) + 1
    outcomes = p_data.get("outcomes", [])
    outcomes.append(outcome)
    p_data["outcomes"] = outcomes[-20:]  # rolling window of 20
    calib["last_calibration"] = db.now()
    await config.set_setting("memory.calibration", json.dumps(calib))


# ── Identity drift analysis (quarterly) ──────────────────────────────────────

@jobs.register("memory_drift")
async def analyze_drift(payload: dict | None = None):
    """Quarterly job: detect identity/attribute drift from supersession chains.

    Produces at most 3 drift observations as modality=insight atoms.
    These NEVER appear in chat context (G5f invariant).
    """
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
        return

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
        '[{"observation":"<text>","evidence_ids":["<atom_id1>"]}]\n\n'
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
    s, e = raw.find("["), raw.rfind("]")
    if s == -1:
        return
    try:
        observations = json.loads(raw[s:e + 1])
    except Exception:
        return

    for obs in observations[:3]:
        if not isinstance(obs, dict) or not obs.get("observation"):
            continue
        await memory.add_atom(
            text=obs["observation"],
            type_="fact",
            source_kind="system",
            modality="insight",
            confidence=0.7,
            meta={"evidence": obs.get("evidence_ids", []), "kind": "drift_observation"},
        )

    # Also run quarterly strand clustering proposal
    try:
        from services.strands import propose_strand_clusters
        await propose_strand_clusters()
    except Exception:
        pass


# ── Goal staleness check (weekly) ─────────────────────────────────────────────

@jobs.register("memory_goal_stale")
async def check_stale_goals(payload: dict | None = None):
    """Open a review question for plans/desires untouched for 90 days."""
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

    for goal in stale_goals:
        # Skip if already suppressed
        topic_key = f"goal:{goal.get('text', '')[:80]}"
        if await is_suppressed(topic_key):
            continue
        # Skip if already open question for this atom
        existing = await db.fetchall(
            "SELECT id FROM memory_question WHERE status='open' AND atom_ids LIKE ?",
            (f'%{goal["id"]}%',),
        )
        if existing:
            continue

        age_days = (db.now() - (goal.get("last_used_at") or goal["created_at"])) // 86400
        prompt = (
            f"Still planning to: \"{goal['text'][:100]}\"? "
            f"(Last updated {age_days} days ago)"
        )
        await q_svc.open_question("goal_check", [goal["id"]], prompt)


def register_schedule():
    """Register Tier 3 periodic jobs."""
    jobs.add_periodic(
        lambda: jobs.enqueue("memory_hypotheses"),
        seconds=7 * 86400,
        job_id="memory_hypotheses",
    )
    jobs.add_periodic(
        lambda: jobs.enqueue("memory_drift"),
        seconds=90 * 86400,
        job_id="memory_drift",
    )
    jobs.add_periodic(
        lambda: jobs.enqueue("memory_goal_stale"),
        seconds=7 * 86400,
        job_id="memory_goal_stale",
    )
    jobs.add_periodic(
        lambda: jobs.enqueue("memory_suppression_pass"),
        seconds=7 * 86400,
        job_id="memory_suppression_pass",
    )
