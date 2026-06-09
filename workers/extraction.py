"""Memory extraction + consolidation jobs (Part 2.2).

Extraction runs the CHEAP model over a finished chat turn, pulls durable facts
about the user, and writes them as atoms (deduped). It is strictly background —
never on the reply path (hot-path rule 1).

Consolidation is the periodic janitor: merge exact duplicates, drop atoms whose
source turn was deleted, and cap unbounded growth. No self-correction / decay /
version chains in v1 (those are Part 6).
"""
from __future__ import annotations

import json

from services import db, llm, memory
from . import jobs

MAX_ATOMS = 50_000  # safety cap; consolidation trims oldest low-salience beyond this

_EXTRACT_SYSTEM = (
    "You extract durable, reusable facts about the USER from a conversation turn. "
    "Return ONLY a JSON array (no prose, no code fences). Each item: "
    '{"text":"<single concise fact, third person about the user>",'
    '"type":"<preference|identity|goal|fact|project|contact>",'
    '"salience":<0.1-1.0>}. '
    "Only include things worth remembering across sessions (preferences, identity, "
    "goals, ongoing projects, key facts). If nothing is worth keeping, return []."
)


def _parse_json_array(raw: str):
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


@jobs.register("extract_memory")
async def extract_memory(payload: dict):
    user_text = (payload.get("user_text") or "").strip()
    assistant_text = (payload.get("assistant_text") or "").strip()
    if not user_text and not assistant_text:
        return
    source_kind = payload.get("source_kind", "chat")
    source_id   = payload.get("source_id")
    project_id  = payload.get("project_id") or None

    convo = f"User: {user_text}\nAssistant: {assistant_text}".strip()
    try:
        raw = await llm.cheap(
            [{"role": "system", "content": _EXTRACT_SYSTEM},
             {"role": "user", "content": convo}],
            temperature=0.1, max_tokens=400,
        )
    except Exception:
        return  # no model available; extraction simply doesn't happen this turn

    for item in _parse_json_array(raw):
        text = (item.get("text") or "").strip()
        if not text:
            continue
        salience = item.get("salience")
        try:
            salience = float(salience)
        except (TypeError, ValueError):
            salience = 1.0
        await memory.add_atom(
            text=text, type_=item.get("type", "fact"),
            source_kind=source_kind, source_id=source_id,
            salience=salience, dedup=True, project_id=project_id,
        )


@jobs.register("consolidate_memory")
async def consolidate_memory(payload: dict | None = None):
    # 1. Drop exact-duplicate texts (keep the oldest / most-pinned).
    dupes = await db.fetchall(
        "SELECT text, COUNT(*) AS n FROM memory_atom GROUP BY text HAVING n > 1"
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
            "SELECT id FROM memory_atom WHERE pinned=0 ORDER BY salience ASC, created_at ASC LIMIT ?",
            (overflow,),
        )
        for v in victims:
            await memory.delete_atom(v["id"])


def register_schedule():
    """Run consolidation every 6 hours."""
    jobs.add_periodic(
        lambda: jobs.enqueue("consolidate_memory"),
        seconds=6 * 3600,
        job_id="consolidate_memory",
    )
