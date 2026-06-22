"""W6 — extraction visibility & steering.

DB-backed, no model. Validates the steering spine: the review queue surfaces what
extraction learned, accept dismisses it, edit changes it, and — the key
acceptance gate — a REJECTION measurably influences subsequent extraction (the
rejected triple is not silently re-learned).

Run:  python -m scripts.test_steering
"""
import asyncio

from services import db, memory
from workers.extraction import _reconcile_before_insert


async def run():
    await db.init_db()
    passed = []

    def ok(name):
        passed.append(name)
        print(f"  PASS: {name}")

    # ── Review queue surfaces extraction output ───────────────────────────────
    fact = await memory.add_atom(
        "Clay uses Postgres for the main database", type_="fact",
        source_kind="chat", source_id="sess-test-w6",
        subject="user", predicate="uses_tool", predicate_category="multi_valued",
        object_val="postgres", modality="factual", confidence=0.9,
    )
    queue = await memory.list_unreviewed_facts(limit=50)
    assert any(a["id"] == fact["id"] for a in queue), "new fact not in review queue"
    ok("review queue surfaces freshly-extracted facts")

    # ── Accept dismisses from the queue (still believed) ──────────────────────
    await memory.mark_reviewed(fact["id"])
    queue2 = await memory.list_unreviewed_facts(limit=50)
    assert not any(a["id"] == fact["id"] for a in queue2), "accepted fact still in queue"
    still = await memory.get_atom(fact["id"])
    assert (still.get("status") or "active") == "active", "accepting must not unbelieve a fact"
    ok("accept dismisses from queue, fact stays believed")

    # ── Reject → rejection signal → influences future extraction (gate) ───────
    # Use a triple with NO existing atom so the test isolates the suppression
    # gate from ordinary corroboration/supersede behaviour.
    item = {"subject": "user", "predicate": "likes", "object": "anchovies",
            "predicate_category": "multi_valued", "confidence": 0.8, "polarity": 0.5}
    action_before = await _reconcile_before_insert(dict(item), None)
    assert action_before != "skip", "should insert before any rejection"

    # Reject (what the /memory/review reject endpoint does for a stated fact).
    await memory.add_rejection_signal(
        {"subject": "user", "predicate": "likes", "object": "anchovies"})
    assert await memory.is_extraction_suppressed("user", "likes", "anchovies")

    action_after = await _reconcile_before_insert(dict(item), None)
    assert action_after == "skip", "rejection did NOT influence subsequent extraction"
    ok("rejection measurably influences subsequent extraction (re-learn suppressed)")

    # ── Reject of a proposed inference routes through the inference lifecycle ──
    src = await memory.add_atom("Clay shipped a feature at 3am", type_="fact",
                                source_kind="chat", source_id="sess-test-w6",
                                subject="user", predicate="worked_late")
    inf = await memory.add_inference(
        "Clay tends to ship under deadline pressure", source_atom_ids=[src["id"]],
        kind="pattern", subject="user", predicate="work_style", object_val="deadline",
    )
    assert inf["status"] == "proposed"
    await memory.reject_inference(inf["id"])
    assert (await memory.get_atom(inf["id"]))["status"] == "rejected"
    ok("rejecting a proposed inference suppresses it (lifecycle reused)")

    # ── cleanup ───────────────────────────────────────────────────────────────
    for aid in (fact["id"], src["id"], inf["id"]):
        await memory.delete_atom(aid)
    await db.execute("DELETE FROM app_config WHERE key='memory.extraction_suppressions'")

    print(f"\nAll W6 steering tests passed! ({len(passed)} checks)")


if __name__ == "__main__":
    asyncio.run(run())
