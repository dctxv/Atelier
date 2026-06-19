"""Memory extraction + consolidation jobs — Living Memory v2.

Extraction runs the CHEAP model over a finished chat turn, pulls structured
facts about the user, and writes them as atoms (deduped + reconciled). It is
strictly background — never on the reply path (hot-path rule 1).

Two-level gating system prevents wasting model calls on phatic turns:
  1. Hot-path gate in the chat router (min chars + FP signal check).
  2. Worker gate here: rule-based significance score, with a tiny model
     call only in the ambiguous band.

Consolidation is the periodic janitor.
"""
from __future__ import annotations

import json
import re
import uuid

from services import db, llm, memory, config
from . import jobs

MAX_ATOMS = 50_000

# ── Significance gating ───────────────────────────────────────────────────────

_FP_RE = re.compile(
    r"\b(i|my|me|i'm|i've|i'll|i'd|we're|i am|i have|i will|i do|i use|"
    r"i work|i like|i love|i hate|i want|i need|i went|i got|i think|"
    r"i feel|i prefer)\b",
    re.IGNORECASE,
)

_PREF_WORDS = frozenset({
    "prefer", "love", "hate", "like", "dislike", "enjoy", "use", "work",
    "live", "want", "need", "plan", "going to", "moving", "started", "quit",
    "hired", "fired", "married", "born", "called", "named",
})

# Self-disclosure verbs that signal a durable fact even WITHOUT a first-person
# pronoun ("Prefers small groups", "Grew up in Dublin", "Struggles to say no").
# Deliberately scoped to trait / preference / life-event verbs so impersonal
# technical prose ("Mamba uses state-space models") does not match.
_DISCLOSURE_RE = re.compile(
    r"\b(prefers?|likes?|loves?|hates?|dislikes?|enjoys?|values?|fears?|"
    r"believes?|feels?|struggles?|tends? to|grew up|raised|moved|quit|"
    r"started|building|built|returned|studies|studying|lives?|living|"
    r"works? as|identifies? as|diagnosed|always|never)\b",
    re.IGNORECASE,
)

# A proper noun appearing mid-sentence (not the first token) is weak evidence of
# a personal entity (a name, place, employer). Capped low so it can only nudge
# content into the model-checked band, never auto-extract on its own.
_MIDCAP_RE = re.compile(r"(?<=[a-z,;:]\s)[A-Z][a-zA-Z]{2,}")


def _significance_score(user_text: str) -> float:
    """Rule-based significance score in [0, 1] for extraction gating.

    First-person pronoun density is the strongest signal, but it is no longer
    the *only* one: self-disclosure verbs and mid-sentence proper nouns let
    impersonally-phrased disclosures ("Prefers small groups") reach at least the
    ambiguous band (model-checked) instead of being hard-dropped. Weights are
    tuned so impersonal technical/trivia prose stays below the 0.7 auto-extract
    bar and is adjudicated by the cheap model.
    """
    if not user_text:
        return 0.0
    text = user_text.strip()
    length_score = min(1.0, len(text) / 200)
    words = text.split()
    fp_density = len(_FP_RE.findall(text)) / max(1, len(words))
    fp_score = min(1.0, fp_density * 5)
    pref_score = 0.3 if any(w in text.lower() for w in _PREF_WORDS) else 0.0
    disclosure_score = 0.2 if _DISCLOSURE_RE.search(text) else 0.0
    entity_score = 0.08 if _MIDCAP_RE.search(text) else 0.0
    # Code/technical content is less likely to contain personal facts
    code_penalty = -0.2 if ("```" in text or re.search(r"\bdef \b|\bclass \b|\bimport \b", text)) else 0.0
    return max(0.0, min(1.0,
        length_score * 0.3 + fp_score * 0.5 + pref_score
        + disclosure_score + entity_score + code_penalty))


# ── Extraction v2 prompt ──────────────────────────────────────────────────────

_EXTRACT_SYSTEM = '''\
You extract durable, structured facts about the USER from a conversation turn.
Return ONLY a JSON array (no prose, no code fences).

Each item is EITHER a fact object OR a retraction object.

FACT object:
{
  "text": "<single concise fact, ENGLISH, third person, e.g. 'Clay works at Acme Corp'>",
  "subject": "<entity the fact is about, lowercase; 'user' for the user themselves>",
  "predicate": "<relationship, lowercase, e.g. 'employer', 'likes', 'lives_in', 'hobby'>",
  "predicate_category": "<functional|multi_valued|comparative|experiential|attribute>",
  "object": "<the value, e.g. 'Acme Corp', 'coffee', 'Sydney'>",
  "polarity": <-1.0 to +1.0, sentiment toward object; 0=neutral>,
  "intensity": <0.0 to 1.0, strength of assertion>,
  "modality": "<factual|opinion|desire|plan|self_perception|hypothetical|commitment>",
  "confidence": <0.0 to 1.0, certainty>,
  "temporal_raw": "<raw time phrase or null>",
  "salience": <0.1 to 1.0, importance>
}

RETRACTION object (when user explicitly corrects or negates something):
{"retract": true, "subject": "<subject>", "predicate": "<predicate>", "object": "<value or null>"}

predicate_category rules:
- functional: one value at a time (employer, lives_in, partner, name, job_title)
- multi_valued: many ok simultaneously (likes, hobby, skill, uses_tool, working_on)
- comparative: rank/superlative — new supersedes old (favorite_x, prefers_x_over_y)
- experiential: accumulating past events — never conflicts (visited, completed, tried)
- attribute: evolving traits with time ranges (trait, communication_style, skill_level)

Additional rules:
1. Polarity vs intensity: "like" and "love" = same positive polarity, different intensities.
2. Negation: "I don't drink coffee" → retraction or negative-polarity fact; NEVER a bare positive.
3. Sarcasm: when sentiment and literal content are incongruent → confidence ≤ 0.3.
4. Hyperbole: "told him a million times" is rhetorical — do NOT extract a quantity.
5. Layered emotions: "excited but scared" → TWO opinion atoms with distinct polarities.
6. Hypothetical/plan/desire: use modality field appropriately.
7. Third parties: subject=<name>, confidence ×0.8.
8. Linguistic certainty: "I think maybe" ≈ 0.4; flat declaratives ≈ 0.9.
   Modality caps: factual≤0.95, plan≤0.85, desire≤0.80, hypothetical≤0.60.
9. Always render text in ENGLISH.
10. Assistant promises: "I'll remind you at 9pm" → modality="commitment".
11. Only extract things worth remembering across sessions. If nothing: return [].
'''

_SIGNIFICANCE_SYSTEM = (
    "Is this conversation turn personally significant? "
    "Reply ONLY 'yes' or 'no'. Significant = reveals durable facts about "
    "the user's identity, preferences, work, relationships, or goals."
)


def _parse_json_array(raw: str) -> list:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        return json.loads(raw[start : end + 1])
    except Exception:
        return []


async def _get_config(key: str, default):
    val = await config.get_setting(key)
    if val is None:
        return default
    try:
        return type(default)(val)
    except Exception:
        return default


# ── Reconciliation (M1 foundation — full M2 reconciliation is in memory.py) ───

async def _reconcile_before_insert(item: dict, project_id: str | None) -> str:
    """Return 'insert' or 'skip'. Side-effects: may corroborate or annotate item."""
    subject = (item.get("subject") or "").lower().strip()
    predicate = (item.get("predicate") or "").lower().strip()
    obj = (item.get("object") or "").strip()
    category = item.get("predicate_category", "")
    confidence = item.get("confidence") or 0.9
    polarity = item.get("polarity") or 0.0
    non_literal = item.get("non_literal", False)

    if not subject or not predicate or non_literal:
        return "insert"

    # Find existing active atoms with same (subject, predicate)
    existing_rows = await db.fetchall(
        "SELECT * FROM memory_atom "
        "WHERE subject=? AND predicate=? AND (status='active' OR status IS NULL)",
        (subject, predicate),
    )
    if not existing_rows:
        return "insert"

    for row in existing_rows:
        row_obj = (row.get("object") or "").strip()
        row_polarity = row.get("polarity") or 0.0
        same_obj = row_obj.lower() == obj.lower() if obj else True
        same_sign = (row_polarity >= 0) == (polarity >= 0)
        if same_obj and same_sign:
            # Corroboration: same fact re-stated
            await memory.corroborate_atom(row["id"])
            return "skip"

    # For functional and comparative predicates, new supersedes old on insert
    if category in ("functional", "comparative"):
        item["_supersede_ids"] = [r["id"] for r in existing_rows]

    return "insert"


# ── Main extraction job ───────────────────────────────────────────────────────

@jobs.register("extract_memory")
async def extract_memory(payload: dict):
    user_text = (payload.get("user_text") or "").strip()
    assistant_text = (payload.get("assistant_text") or "").strip()
    memory_off = payload.get("memory_off", False)

    if memory_off or (not user_text and not assistant_text):
        return

    # Tier gate: block only if explicitly disabled.
    # If never configured (None), auto-enable at basic so extraction works out of the box.
    tier_raw = await config.get_setting("memory.tier_selected")
    if tier_raw is None:
        await config.set_setting("memory.tier_selected", "true")
        await config.set_setting("memory.tier", "basic")
        await config.set_setting("memory.depth", "basic")
    elif str(tier_raw).lower() != "true":
        return

    source_kind = payload.get("source_kind", "chat")
    source_id   = payload.get("source_id")
    project_id  = payload.get("project_id") or None

    # Update slot pattern vector for warming (P1.4 §5.3) — pure local math
    if user_text and source_kind == "chat":
        try:
            from services.warming import update_slot_pattern
            import asyncio
            asyncio.create_task(update_slot_pattern(source_id or "", user_text))
        except Exception:
            pass

    # Worker-level significance gate
    signif_low  = await _get_config("memory.signif_low",  0.3)
    signif_high = await _get_config("memory.signif_high", 0.7)
    score = _significance_score(user_text)

    if score < signif_low:
        return  # clearly not significant

    if score < signif_high:
        # Ambiguous band: ask model for a quick yes/no
        try:
            verdict = await llm.cheap(
                [
                    {"role": "system", "content": _SIGNIFICANCE_SYSTEM},
                    {"role": "user", "content": user_text[:500]},
                ],
                temperature=0.0,
                max_tokens=5,
            )
            if "no" in (verdict or "").lower():
                return
        except Exception:
            pass  # model unavailable → proceed with extraction

    # Include current date for temporal resolution
    import datetime
    current_date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    system_prompt = _EXTRACT_SYSTEM + f"\n\nCurrent date: {current_date}"
    convo = f"User: {user_text}\nAssistant: {assistant_text}".strip()

    try:
        raw = await llm.cheap(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": convo},
            ],
            temperature=0.1,
            max_tokens=800,
        )
    except Exception:
        return  # no model available; extraction simply doesn't happen this turn

    items = _parse_json_array(raw)

    for item in items:
        if not isinstance(item, dict):
            continue

        # Handle retraction objects
        if item.get("retract"):
            subj = (item.get("subject") or "").lower().strip()
            pred = (item.get("predicate") or "").lower().strip()
            obj  = (item.get("object") or "").strip()
            if subj and pred:
                q = (
                    "SELECT id FROM memory_atom "
                    "WHERE subject=? AND predicate=? AND (status='active' OR status IS NULL)"
                )
                params: tuple = (subj, pred)
                if obj:
                    q += " AND LOWER(object)=?"
                    params = (subj, pred, obj.lower())
                rows = await db.fetchall(q, params)
                for r in rows:
                    await memory.retract_atom(r["id"], "user_correction")
            continue

        text = (item.get("text") or "").strip()
        if not text:
            continue

        # Parse numeric fields with safe fallbacks
        def _clamp(val, lo, hi, fallback):
            try:
                return max(lo, min(hi, float(val)))
            except (TypeError, ValueError):
                return fallback

        salience    = _clamp(item.get("salience"), 0.1, 1.0, 1.0)
        confidence  = _clamp(item.get("confidence"), 0.1, 1.0, 0.9)
        polarity    = _clamp(item.get("polarity"), -1.0, 1.0, 0.0)
        intensity   = _clamp(item.get("intensity"), 0.0, 1.0, 0.5)

        subject   = (item.get("subject") or "").lower().strip() or None
        predicate = (item.get("predicate") or "").lower().strip() or None
        pred_cat  = item.get("predicate_category") or None
        obj       = item.get("object") or None
        modality  = item.get("modality") or "factual"
        temp_raw  = item.get("temporal_raw")

        # Modality caps confidence ceiling
        _mod_caps = {"factual": 0.95, "plan": 0.85, "desire": 0.80, "hypothetical": 0.60}
        confidence = min(confidence, _mod_caps.get(modality, 0.95))

        # Third-party dampening
        if subject and subject != "user":
            confidence = min(confidence, confidence * 0.8)

        # Build meta
        meta: dict = {}
        if confidence <= 0.3:
            meta["non_literal"] = True
        if item.get("transition_signal"):
            meta["transition_signal"] = True

        item["subject"]            = subject
        item["predicate"]          = predicate
        item["predicate_category"] = pred_cat
        item["object"]             = obj
        item["confidence"]         = confidence
        item["polarity"]           = polarity
        item["non_literal"]        = meta.get("non_literal", False)

        # Pre-insert reconciliation
        action = await _reconcile_before_insert(item, project_id)
        if action == "skip":
            continue

        atom = await memory.add_atom(
            text=text,
            type_=item.get("type", "fact"),
            source_kind=source_kind,
            source_id=source_id,
            salience=salience,
            dedup=True,
            project_id=project_id,
            subject=subject,
            predicate=predicate,
            predicate_category=pred_cat,
            object_val=obj,
            polarity=polarity,
            intensity=intensity,
            modality=modality,
            confidence=confidence,
            temporal_raw=temp_raw,
            meta=meta if meta else None,
        )

        # Supersede old atoms for functional/comparative predicates
        for old_id in item.get("_supersede_ids", []):
            if atom and atom["id"] != old_id:
                await memory.supersede_atom(old_id, atom["id"])

        # Route commitments with a due time to the task table
        if modality == "commitment" and assistant_text:
            await _route_commitment(atom, source_id)

        # Hypothesis testing (Fix 5) — only for prescient tier, never on the hot path
        # (extraction is already background; hypothesis testing is a cheap model call)
        if atom and modality not in ("hypothesis", "insight") and source_kind == "chat":
            if await config.get_setting("memory.tier") == "prescient":
                from workers.memory_prescient import test_hypotheses_against_atom
                import asyncio
                asyncio.create_task(test_hypotheses_against_atom(atom))


async def _route_commitment(atom: dict, session_id: str | None) -> None:
    """Create a task row for an assistant commitment atom."""
    try:
        ts = db.now()
        task_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO task(id, title, description, status, priority, created_at, updated_at, source_kind, source_id) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (
                task_id,
                atom["text"][:200],
                f"Assistant commitment from session {session_id or 'unknown'}",
                "todo",
                "medium",
                ts,
                ts,
                "assistant_commitment",
                atom["id"],
            ),
        )
    except Exception:
        pass  # task creation is best-effort; never break extraction


# ── Consolidation (periodic janitor) ─────────────────────────────────────────

@jobs.register("consolidate_memory")
async def consolidate_memory(payload: dict | None = None):
    # 1. Drop exact-duplicate texts (keep the oldest / most-pinned).
    dupes = await db.fetchall(
        "SELECT text, COUNT(*) AS n FROM memory_atom "
        "WHERE status='active' OR status IS NULL GROUP BY text HAVING n > 1"
    )
    for d in dupes:
        rows = await db.fetchall(
            "SELECT id FROM memory_atom WHERE text=? ORDER BY pinned DESC, created_at ASC",
            (d["text"],),
        )
        for extra in rows[1:]:
            await memory.delete_atom(extra["id"])

    # 2. Drop atoms whose chat source turn no longer exists.
    orphans = await db.fetchall(
        "SELECT id FROM memory_atom WHERE source_kind='chat' AND source_id IS NOT NULL "
        "AND source_id NOT IN (SELECT id FROM session)"
    )
    for o in orphans:
        await memory.delete_atom(o["id"])

    # 3. Cap growth: beyond MAX_ATOMS, drop oldest unpinned low-salience atoms.
    total = await memory.count()
    if total > MAX_ATOMS:
        overflow = total - MAX_ATOMS
        victims = await db.fetchall(
            "SELECT id FROM memory_atom WHERE pinned=0 AND (status='active' OR status IS NULL) "
            "ORDER BY salience ASC, created_at ASC LIMIT ?",
            (overflow,),
        )
        for v in victims:
            await memory.delete_atom(v["id"])

    # 4. Archive atoms whose valid_until has passed.
    now_ts = db.now()
    expired = await db.fetchall(
        "SELECT id FROM memory_atom WHERE valid_until IS NOT NULL AND valid_until < ? "
        "AND status='active'",
        (now_ts,),
    )
    for e in expired:
        await db.execute(
            "UPDATE memory_atom SET status='archived' WHERE id=?", (e["id"],)
        )
        await memory.log_event(e["id"], "retracted", {"reason": "valid_until_expired"})
    if expired:
        await db.bump_mutation_seq()


# ── Calibration job (weekly) ──────────────────────────────────────────────────

@jobs.register("calibrate_memory")
async def calibrate_memory(payload: dict | None = None):
    """Read recent resolution events and update calibration blob in app_config."""
    # Read conflicts resolved in the past 7 days
    cutoff = db.now() - 7 * 86400
    events = await db.fetchall(
        "SELECT * FROM memory_event WHERE kind IN ('conflict_resolved','clarified') "
        "AND created_at > ? LIMIT 500",
        (cutoff,),
    )
    if not events:
        return

    # Per-predicate-category accuracy tracking (simplified)
    import json as _json
    raw_blob = await config.get_setting("memory.calibration")
    calib: dict = {}
    if raw_blob:
        try:
            calib = _json.loads(raw_blob)
        except Exception:
            calib = {}

    # Count resolutions and update accuracy approximation
    resolutions = len(events)
    calib["last_calibration"] = db.now()
    calib["resolutions_7d"] = resolutions

    await config.set_setting("memory.calibration", _json.dumps(calib))


def register_schedule():
    """Register periodic jobs."""
    jobs.add_periodic(
        lambda: jobs.enqueue("consolidate_memory"),
        seconds=6 * 3600,
        job_id="consolidate_memory",
    )
    jobs.add_periodic(
        lambda: jobs.enqueue("calibrate_memory"),
        seconds=7 * 86400,
        job_id="calibrate_memory",
    )
