"""Weekly memory digest (P1.6) — transparent summary of what the system has done.

A weekly job that produces a note (source_kind='memory_diff') summarising
the past 7 days of memory events.  The note appears in the Notes surface
like any other note and is never re-ingested into memory atoms.

Failure handling: if the cheap-model call fails, a simple template-rendered
fallback is written so the user always gets a digest.

[VALIDATE] memory.weekly_diff_atom_cap (default 12) after real usage data.
"""
from __future__ import annotations

import datetime
import json

from services import config, db, llm, memory as memory_svc
from services.notes import upsert_diff_note
from workers import jobs


async def _get_cfg(key: str, default):
    val = await config.get_setting(key)
    if val is None:
        return default
    try:
        return type(default)(val)
    except Exception:
        return default


async def _is_suppressed(topic_key: str) -> bool:
    row = await db.fetchone(
        "SELECT confidence FROM memory_atom "
        "WHERE predicate='suppressed' AND subject=? "
        "AND (status='active' OR status IS NULL)",
        (topic_key,),
    )
    return bool(row and (row.get("confidence") or 0.0) >= 0.6)


@jobs.register("memory_weekly_diff")
async def generate_weekly_diff(payload: dict | None = None):
    """Generate and upsert the weekly memory digest note."""
    atom_cap = int(await _get_cfg("memory.weekly_diff_atom_cap", 12))

    now_ts = db.now()
    week_ago = now_ts - 7 * 86400

    # Week range for title
    start_dt = datetime.datetime.utcfromtimestamp(week_ago)
    end_dt = datetime.datetime.utcfromtimestamp(now_ts)
    week_start_iso = start_dt.strftime("%Y-%m-%d")
    title_range = f"{start_dt.strftime('%-d %b')} – {end_dt.strftime('%-d %b %Y')}"
    note_title = f"Memory digest — {title_range}"

    # ── Data gathering (rule-based, no model call) ────────────────────────────

    # 1. New facts count
    new_events = await db.fetchall(
        "SELECT e.*, a.text, a.confidence FROM memory_event e "
        "JOIN memory_atom a ON a.id = e.atom_id "
        "WHERE e.kind='created' AND e.created_at > ?",
        (week_ago,),
    )
    new_facts_count = len(new_events)

    # 2. Notable created atoms (confidence >= 0.7, salience-sorted, capped)
    notable_atoms = sorted(
        [e for e in new_events if (e.get("confidence") or 0.0) >= 0.7],
        key=lambda x: (x.get("confidence") or 0.0),
        reverse=True,
    )[:min(3, atom_cap)]
    notable_texts = []
    for e in notable_atoms:
        text = e.get("text", "")
        # Skip suppressed topics
        if not await _is_suppressed(text[:80]):
            notable_texts.append(text)

    # 3. Supersessions
    supersession_events = await db.fetchall(
        "SELECT e.*, a.text AS old_text FROM memory_event e "
        "JOIN memory_atom a ON a.id = e.atom_id "
        "WHERE e.kind='superseded' AND e.created_at > ?",
        (week_ago,),
    )
    supersessions = []
    for ev in supersession_events[:5]:
        detail = json.loads(ev.get("detail") or "{}")
        new_id = detail.get("superseded_by")
        if new_id:
            new_atom = await memory_svc.get_atom(new_id)
            if new_atom:
                supersessions.append((ev.get("old_text", ""), new_atom.get("text", "")))

    # 4. Questions opened / closed
    qs_opened = await db.fetchall(
        "SELECT id FROM memory_question WHERE created_at > ?", (week_ago,)
    )
    qs_closed = await db.fetchall(
        "SELECT id FROM memory_question WHERE resolved_at > ? AND status != 'open'",
        (week_ago,),
    )

    # 5. Hypothesis events
    hyp_events = await db.fetchall(
        "SELECT kind, COUNT(*) AS n FROM memory_event "
        "WHERE kind IN ('hypothesis_confirmed','hypothesis_refuted','hypothesis_expired') "
        "AND created_at > ? GROUP BY kind",
        (week_ago,),
    )
    hyp_map = {e["kind"]: e["n"] for e in hyp_events}

    # 6. Compacted
    compacted = await db.fetchall(
        "SELECT COUNT(*) AS n FROM memory_event WHERE kind='retracted' AND created_at > ?",
        (week_ago,),
    )
    compacted_count = compacted[0]["n"] if compacted else 0

    # ── Check for no events ───────────────────────────────────────────────────
    has_any = bool(new_facts_count or supersessions or qs_closed or
                   hyp_map or compacted_count)

    if not has_any:
        body = "No memory changes this week."
        await upsert_diff_note(week_start_iso, note_title, body)
        return

    # ── Build data summary for model ──────────────────────────────────────────
    data_lines = [f"Facts recorded this week: {new_facts_count}"]
    if notable_texts:
        data_lines.append("Notable new facts:")
        for t in notable_texts:
            data_lines.append(f"  · {t}")
    if supersessions:
        data_lines.append("Updates (old → new):")
        for old, new in supersessions[:3]:
            data_lines.append(f"  - {old[:60]} -> {new[:60]}")
    if qs_opened:
        data_lines.append(f"Review questions opened: {len(qs_opened)}")
    if qs_closed:
        data_lines.append(f"Review questions resolved: {len(qs_closed)}")
    if hyp_map.get("hypothesis_confirmed"):
        data_lines.append(f"Hypotheses confirmed: {hyp_map['hypothesis_confirmed']}")
    if hyp_map.get("hypothesis_refuted"):
        data_lines.append(f"Hypotheses refuted: {hyp_map['hypothesis_refuted']}")
    if compacted_count:
        data_lines.append(f"Stale facts removed: {compacted_count}")

    data_str = "\n".join(data_lines)

    prompt = (
        "Summarise this week's memory system activity as short Markdown bullet points. "
        "Rules:\n"
        "1. List factual changes only — no interpretation or advice.\n"
        "2. Keep each bullet to one line.\n"
        "3. End with exactly this line if there were any changes: 'Memory actively maintained.'\n"
        "4. If there were no changes, output only: 'No memory changes this week.'\n"
        "5. Maximum 10 bullets total.\n\n"
        f"Activity data:\n{data_str}"
    )

    try:
        body = await llm.cheap(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=300,
            task="weekly_diff_summary",
        )
        body = (body or "").strip()
        if not body:
            raise ValueError("empty response")
    except Exception:
        # Fallback: plain template rendering (always succeeds)
        body = _template_fallback(
            new_facts_count, notable_texts, supersessions,
            len(qs_opened), len(qs_closed), hyp_map, compacted_count,
        )

    await upsert_diff_note(week_start_iso, note_title, body)


def _template_fallback(
    new_count: int,
    notable: list,
    supersessions: list,
    q_opened: int,
    q_closed: int,
    hyp_map: dict,
    compacted: int,
) -> str:
    lines = []
    if new_count:
        lines.append(f"- {new_count} new fact{'s' if new_count != 1 else ''} recorded.")
    for text in notable[:3]:
        lines.append(f"- New: {text[:80]}")
    for old, new in supersessions[:3]:
        lines.append(f"- Updated: {old[:50]} -> {new[:50]}")
    if q_opened:
        lines.append(f"- {q_opened} review question{'s' if q_opened != 1 else ''} opened.")
    if q_closed:
        lines.append(f"- {q_closed} review question{'s' if q_closed != 1 else ''} resolved.")
    c = hyp_map.get("hypothesis_confirmed", 0)
    r = hyp_map.get("hypothesis_refuted", 0)
    if c:
        lines.append(f"- {c} hypothesis confirmed.")
    if r:
        lines.append(f"- {r} hypothesis refuted.")
    if compacted:
        lines.append(f"- {compacted} stale fact{'s' if compacted != 1 else ''} removed.")
    lines.append("Memory actively maintained.")
    return "\n".join(lines) if lines else "No memory changes this week."


def register_schedule():
    """Register weekly diff job (Sunday 00:00 UTC approximated as weekly cadence)."""
    jobs.add_periodic(
        lambda: jobs.enqueue("memory_weekly_diff"),
        seconds=7 * 86400,
        job_id="memory_weekly_diff",
    )
