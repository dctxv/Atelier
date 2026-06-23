"""Memory intake discipline fixture tests.

Run:  python -m scripts.test_intake_discipline

Uses a temporary SQLite DB, never data/atelier.db.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from services import config, db, memory
from workers import extraction, memory_inference
from workers.clustering import cluster_memory


async def _fact(
    text: str,
    *,
    source_id: str,
    confidence: float = 0.9,
    predicate: str = "works_at_night",
) -> dict:
    return await memory.add_atom(
        text,
        type_="fact",
        source_kind="chat",
        source_id=source_id,
        subject="user",
        predicate=predicate,
        predicate_category="multi_valued",
        modality="factual",
        confidence=confidence,
    )


async def _count_insights() -> int:
    row = await db.fetchone("SELECT COUNT(*) AS n FROM memory_atom WHERE modality='insight'")
    return int(row["n"] if row else 0)


async def _test_auto_confirm():
    async def fake_cheap(messages, temperature=0.2, max_tokens=512, task="unknown"):
        content = messages[-1]["content"].lower()
        if "diagnosed" in content:
            return json.dumps([
                {
                    "text": "Clay is diagnosed with ADHD",
                    "subject": "user",
                    "predicate": "diagnosed_with",
                    "predicate_category": "attribute",
                    "object": "ADHD",
                    "polarity": 0,
                    "intensity": 0.7,
                    "modality": "factual",
                    "confidence": 0.95,
                    "temporal_raw": None,
                    "salience": 0.8,
                }
            ])
        return json.dumps([
            {
                "text": "Clay uses DeepSeek for planning",
                "subject": "user",
                "predicate": "uses_tool",
                "predicate_category": "multi_valued",
                "object": "DeepSeek",
                "polarity": 0,
                "intensity": 0.6,
                "modality": "factual",
                "confidence": 0.95,
                "temporal_raw": None,
                "salience": 0.8,
            }
        ])

    extraction.llm.cheap = fake_cheap
    await config.set_setting("memory.tier_selected", "true")
    await config.set_setting("intake.fact_autoconfirm_confidence", 0.90)
    await config.set_setting("intake.inference_significance", 2.0)

    await extraction.extract_memory({
        "user_text": "I use DeepSeek for planning and I want that remembered.",
        "assistant_text": "",
        "source_kind": "chat",
        "source_id": "session-auto",
    })
    row = await db.fetchone("SELECT * FROM memory_atom WHERE predicate='uses_tool'")
    atom = memory._row_to_atom(row)
    assert atom["status"] == "active"
    assert atom["cluster_dirty"] is True
    assert (atom.get("meta") or {}).get("reviewed") is True
    queue = await memory.list_unreviewed_facts(limit=20)
    assert atom["id"] not in {a["id"] for a in queue}
    event = await db.fetchone(
        "SELECT * FROM memory_event WHERE atom_id=? AND kind='reviewed'",
        (atom["id"],),
    )
    assert event is not None
    detail = json.loads(event["detail"])
    assert detail["action"] == "accepted" and detail["reason"] == "auto"

    await extraction.extract_memory({
        "user_text": "I was diagnosed with ADHD and want to keep an eye on it.",
        "assistant_text": "",
        "source_kind": "chat",
        "source_id": "session-sensitive",
    })
    sensitive = memory._row_to_atom(
        await db.fetchone("SELECT * FROM memory_atom WHERE predicate='diagnosed_with'")
    )
    assert not ((sensitive.get("meta") or {}).get("reviewed"))
    queue = await memory.list_unreviewed_facts(limit=20)
    assert sensitive["id"] in {a["id"] for a in queue}

    inf = await memory.add_inference(
        "Clay values low-cost model routing",
        [atom["id"], sensitive["id"]],
        kind="implied_preference",
        subject="user",
        predicate="values",
        object_val="low-cost model routing",
        confidence=0.95,
    )
    assert inf["status"] == "proposed"
    proposed = await memory.list_inferences(status="proposed", limit=20)
    assert inf["id"] in {a["id"] for a in proposed}


async def _test_inference_throttle():
    await config.set_setting("memory.tier_selected", "true")
    await config.set_setting("intake.inference_min_evidence", 2)
    await config.set_setting("intake.inference_budget", 1)

    async def fake_strict(messages, temperature=0.2, max_tokens=512, task="unknown"):
        return json.dumps([
            {
                "kind": "pattern",
                "text": "Clay tends to work late at night",
                "subject": "user",
                "predicate": "work_rhythm",
                "object": "late night",
                "confidence": 0.8,
            }
        ])

    memory_inference.llm.cheap_strict = fake_strict

    same1 = await _fact("Clay pushed commits at 2am", source_id="one-session")
    same2 = await _fact("Clay planned model routing at 1am", source_id="one-session")
    result = await memory_inference.infer_turn({
        "user_text": "I was up late again working on routing.",
        "assistant_text": "",
        "atom_ids": [same1["id"], same2["id"]],
        "source_id": "one-session",
    })
    assert result == []
    assert await _count_insights() == 1  # only the explicit Visibility Law inference from prior test

    a = await _fact("Clay pushed commits at 2am on Monday", source_id="late-a")
    b = await _fact("Clay replied to email at 1:30am on Thursday", source_id="late-b")
    result = await memory_inference.infer_turn({
        "user_text": "I was up late again working on routing.",
        "assistant_text": "",
        "atom_ids": [a["id"], b["id"]],
        "source_id": "late-b",
    })
    assert len(result) == 1

    before = await _count_insights()
    existing = result[0]
    old = await memory.get_atom(existing["id"])
    again = await memory_inference.infer_turn({
        "user_text": "Still up late again working on routing.",
        "assistant_text": "",
        "atom_ids": [a["id"], b["id"]],
        "source_id": "late-b",
    })
    assert len(again) == 1
    assert again[0]["id"] == existing["id"]
    assert await _count_insights() == before

    dup = await memory.add_inference(
        "Clay tends to work late at night",
        [same1["id"], a["id"]],
        kind="pattern",
        subject="user",
        predicate="work_rhythm",
        object_val="late night",
    )
    assert dup["id"] == existing["id"]
    assert await _count_insights() == before
    assert (dup.get("meta") or {}).get("sightings", 0) >= 2
    assert dup["last_used_at"] >= old["last_used_at"]


async def _test_prune_and_strand_cleanup():
    await config.set_setting("prune.confidence_floor", 0.40)
    await config.set_setting("prune.pending_ttl_days", 21)

    stale = await _fact(
        "Clay might someday try a niche editor",
        source_id="old-low",
        confidence=0.2,
        predicate="might_try",
    )
    keep = await _fact(
        "Clay might revisit a niche editor",
        source_id="old-corroborated",
        confidence=0.2,
        predicate="might_revisit",
    )
    old_ts = db.now() - 30 * 86400
    await db.execute(
        "UPDATE memory_atom SET created_at=?, last_used_at=?, strand_id=?, cluster_dirty=0 WHERE id=?",
        (old_ts, old_ts, "stale-strand", stale["id"]),
    )
    await db.execute(
        "UPDATE memory_atom SET created_at=?, last_used_at=?, strand_id=?, cluster_dirty=0 WHERE id=?",
        (old_ts, old_ts + 3600, "keep-strand", keep["id"]),
    )

    pruned = await extraction.prune_memory_review_queue({})
    assert pruned["retired"] >= 1
    stale_row = await db.fetchone("SELECT * FROM memory_atom WHERE id=?", (stale["id"],))
    assert stale_row["status"] == "retired"
    assert stale_row["cluster_dirty"] == 1
    assert await memory.get_atom(stale["id"]) is not None
    keep_row = await db.fetchone("SELECT status FROM memory_atom WHERE id=?", (keep["id"],))
    assert (keep_row["status"] or "active") == "active"

    await cluster_memory({})
    cleaned = await db.fetchone(
        "SELECT strand_id, cluster_dirty FROM memory_atom WHERE id=?", (stale["id"],)
    )
    assert cleaned["strand_id"] is None
    assert cleaned["cluster_dirty"] == 0


async def run():
    with tempfile.TemporaryDirectory() as td:
        try:
            db.configure_for_tests(Path(td) / "atelier-intake-test.db")
            await db.init_db()

            await _test_auto_confirm()
            print("  PASS: high-confidence stated facts auto-review, sensitive facts do not")

            await _test_inference_throttle()
            print("  PASS: per-turn inference requires distinct evidence and dedups pending insights")

            await _test_prune_and_strand_cleanup()
            print("  PASS: stale unreviewed facts soft-retire and leave strands on clustering cleanup")
        finally:
            db.shutdown()

    print("\nAll intake discipline fixture tests passed.")


if __name__ == "__main__":
    asyncio.run(run())
