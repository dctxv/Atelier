"""Emergent memory clustering fixture tests.

Run:  python -m scripts.test_clustering

Uses a temporary SQLite DB, never data/atelier.db.
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from services import config, db, memory, retrieval, strands
from workers.clustering import cluster_memory


ROUTING = [
    "Clay routes coding questions to cheap local models for cost control",
    "Clay compares Sonnet and DeepSeek for model routing decisions",
    "Clay wants routing rules that keep expensive models off routine work",
    "Clay tracks model cost when choosing assistant endpoints",
    "Clay designs model routing around latency and budget",
]

MEMORY_UI = [
    "Clay wants memory review queues to stay visible and honest",
    "Clay prefers memory uncertainty to appear as an explicit unsorted state",
    "Clay cares about memory graph labels staying stable across runs",
    "Clay reviews inferred memories before trusting them in chat",
    "Clay wants memory surfaces to show provenance and confidence",
]

NOISE = [
    "The spare blue umbrella is behind the hallway cabinet",
]


async def _seed():
    for text in ROUTING:
        await memory.add_atom(
            text,
            type_="fact",
            source_kind="fixture",
            subject="user",
            predicate="model_routing",
            predicate_category="multi_valued",
            modality="factual",
            confidence=0.9,
        )
    for text in MEMORY_UI:
        await memory.add_atom(
            text,
            type_="fact",
            source_kind="fixture",
            subject="user",
            predicate="memory_design",
            predicate_category="multi_valued",
            modality="factual",
            confidence=0.9,
        )
    for text in NOISE:
        await memory.add_atom(
            text,
            type_="fact",
            source_kind="fixture",
            subject="user",
            predicate="storage_location",
            predicate_category="multi_valued",
            modality="factual",
            confidence=0.9,
        )


async def run():
    with tempfile.TemporaryDirectory() as td:
        try:
            db.configure_for_tests(Path(td) / "atelier-test.db")
            await db.init_db()
            await db.init_db()

            cols = await db.fetchall("PRAGMA table_info(memory_atom)")
            col_names = {c["name"] for c in cols}
            assert {"strand_id", "strand_assigned_at", "cluster_dirty"} <= col_names
            assert await db.fetchone("SELECT name FROM sqlite_master WHERE type='table' AND name='memory_strands'")
            print("  PASS: migration is idempotent and adds strand storage")

            await config.set_setting("cluster.knn_k", 4)
            await config.set_setting("cluster.sim_threshold", 0.18)
            await config.set_setting("cluster.min_cluster_size", 3)
            await config.set_setting("cluster.max_runtime_ms", 10000)
            await config.set_setting("cheap_model", "")

            await _seed()
            dirty = await db.fetchone("SELECT COUNT(*) AS n FROM memory_atom WHERE cluster_dirty=1")
            assert dirty and dirty["n"] == len(ROUTING) + len(MEMORY_UI) + len(NOISE)
            print("  PASS: add_atom marks atoms dirty")

            snap = await retrieval.memory_knn_snapshot()
            assert snap["matrix"].shape[0] == len(snap["ids"]) >= len(ROUTING)
            print("  PASS: public KNN snapshot exposes matrix, ids, and version")

            first = await cluster_memory({"full": True})
            assert first["ok"], first
            rows = await db.fetchall(
                "SELECT id, text, strand_id, cluster_dirty FROM memory_atom ORDER BY text"
            )
            first_assignments = {r["id"]: r["strand_id"] for r in rows}
            assert all(r["cluster_dirty"] == 0 for r in rows)
            assert sum(1 for sid in first_assignments.values() if sid) >= 6
            assert any(sid is None for sid in first_assignments.values())
            print("  PASS: full pass assigns clustered atoms and leaves true noise unsorted")

            strand_rows = await strands.load_registry(include_dormant=True)
            assert strand_rows
            assert all(s["label"] is None for s in strand_rows), strand_rows
            print("  PASS: labeling fails closed without an explicit cheap model")

            second = await cluster_memory({"full": True})
            assert second["ok"], second
            rows2 = await db.fetchall("SELECT id, strand_id FROM memory_atom ORDER BY text")
            second_assignments = {r["id"]: r["strand_id"] for r in rows2}
            assert first_assignments == second_assignments
            print("  PASS: full clustering is deterministic on unchanged input")

            atom_id = rows2[0]["id"]
            await memory.update_atom(atom_id, text="Clay routes coding questions to cheap local models for cost control")
            dirty_one = await db.fetchone("SELECT cluster_dirty FROM memory_atom WHERE id=?", (atom_id,))
            assert dirty_one and dirty_one["cluster_dirty"] == 1
            await cluster_memory({})
            clean_one = await db.fetchone("SELECT cluster_dirty FROM memory_atom WHERE id=?", (atom_id,))
            assert clean_one and clean_one["cluster_dirty"] == 0
            print("  PASS: vector-affecting updates re-enter the cadence pass")
        finally:
            db.shutdown()

    print("\nAll clustering fixture tests passed.")


if __name__ == "__main__":
    asyncio.run(run())
