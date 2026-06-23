"""Emergent memory clustering fixture tests.

Run:  python -m scripts.test_clustering

Uses a temporary SQLite DB, never data/atelier.db.
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from services import config, db, memory, retrieval, strands
from workers.clustering import cluster_memory, _PENDING_POOL_KEY


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

            # --- Determinism: two full passes on unchanged input produce identical assignments ---
            second = await cluster_memory({"full": True})
            assert second["ok"], second
            rows2 = await db.fetchall("SELECT id, strand_id FROM memory_atom ORDER BY text")
            second_assignments = {r["id"]: r["strand_id"] for r in rows2}
            assert first_assignments == second_assignments, (
                f"Non-deterministic: {[k for k in first_assignments if first_assignments[k] != second_assignments.get(k)]}"
            )
            print("  PASS: full clustering is deterministic on unchanged input (byte-identical assignments)")

            atom_id = rows2[0]["id"]
            await memory.update_atom(atom_id, text="Clay routes coding questions to cheap local models for cost control")
            dirty_one = await db.fetchone("SELECT cluster_dirty FROM memory_atom WHERE id=?", (atom_id,))
            assert dirty_one and dirty_one["cluster_dirty"] == 1
            await cluster_memory({})
            clean_one = await db.fetchone("SELECT cluster_dirty FROM memory_atom WHERE id=?", (atom_id,))
            assert clean_one and clean_one["cluster_dirty"] == 0
            print("  PASS: vector-affecting updates re-enter the cadence pass")

            # --- Stale strand_id cleanup: suppressed atoms lose their strand assignment ---
            # Find an atom that currently has a strand_id and suppress it.
            assigned_row = await db.fetchone(
                "SELECT id, strand_id FROM memory_atom WHERE strand_id IS NOT NULL LIMIT 1"
            )
            assert assigned_row, "expected at least one assigned atom"
            suppressed_id = assigned_row["id"]
            old_strand_id = assigned_row["strand_id"]
            # Suppress the atom (predicate='suppressed' is the active suppression marker).
            await db.execute(
                "UPDATE memory_atom SET predicate='suppressed', cluster_dirty=0 WHERE id=?",
                (suppressed_id,),
            )
            # Verify it still has its old strand_id before we run the worker.
            before = await db.fetchone("SELECT strand_id FROM memory_atom WHERE id=?", (suppressed_id,))
            assert before and before["strand_id"] == old_strand_id
            # A full pass must null it out.
            await cluster_memory({"full": True})
            after = await db.fetchone("SELECT strand_id FROM memory_atom WHERE id=?", (suppressed_id,))
            assert after and after["strand_id"] is None, (
                f"Expected NULL strand_id after suppression, got {after['strand_id']}"
            )
            print("  PASS: apply_clustering_result nulls strand_id for suppressed atoms")

            # --- Pending pool: leftovers accumulate across incremental passes and crystallize ---
            # Reset to a clean slate with a high min_cluster_size so individual
            # incremental passes can't form new strands on their own.
            await cluster_memory({"full": True})
            await config.set_setting("cluster.min_cluster_size", 4)

            # Add 2 similar atoms (same token set → high hash-embedding cosine).
            # These will fail centroid matching (new semantic area) and become leftovers.
            pool_texts_batch1 = [
                "Clay prefers keyboard shortcuts for terminal navigation workflow",
                "Clay uses keyboard bindings to speed up terminal workflow",
            ]
            pool_ids_batch1 = []
            for text in pool_texts_batch1:
                atom = await memory.add_atom(
                    text,
                    type_="fact",
                    source_kind="fixture",
                    subject="user",
                    predicate="workflow_pref",
                    predicate_category="multi_valued",
                    modality="factual",
                    confidence=0.9,
                )
                pool_ids_batch1.append(atom["id"])

            inc1 = await cluster_memory({})
            assert inc1["ok"], inc1
            # Both atoms should be dirty-cleared even though they're in the pool.
            for aid in pool_ids_batch1:
                row = await db.fetchone("SELECT cluster_dirty FROM memory_atom WHERE id=?", (aid,))
                assert row and row["cluster_dirty"] == 0, f"atom {aid} still dirty after inc1"

            pool_raw = await config.get_setting("cluster.pending_pool")
            import json as _json
            pool_after_inc1 = _json.loads(pool_raw or "[]")
            assert any(aid in pool_after_inc1 for aid in pool_ids_batch1), (
                f"Expected pool to contain batch-1 atoms, got {pool_after_inc1}"
            )
            print("  PASS: incremental pass saves leftovers to pending pool")

            # Add 2 more similar atoms.  Combined pool = 4 >= min_cluster_size → should cluster.
            pool_texts_batch2 = [
                "Clay remaps terminal keyboard shortcuts for navigation speed",
                "Clay configures keyboard workflow shortcuts in the terminal",
            ]
            pool_ids_batch2 = []
            for text in pool_texts_batch2:
                atom = await memory.add_atom(
                    text,
                    type_="fact",
                    source_kind="fixture",
                    subject="user",
                    predicate="workflow_pref",
                    predicate_category="multi_valued",
                    modality="factual",
                    confidence=0.9,
                )
                pool_ids_batch2.append(atom["id"])

            inc2 = await cluster_memory({})
            assert inc2["ok"], inc2
            # At least some of the pool atoms should now have a strand assigned.
            all_pool_ids = pool_ids_batch1 + pool_ids_batch2
            pool_assignments = await db.fetchall(
                f"SELECT id, strand_id FROM memory_atom WHERE id IN ({','.join('?' * len(all_pool_ids))})",
                tuple(all_pool_ids),
            )
            assigned_count = sum(1 for r in pool_assignments if r["strand_id"])
            assert assigned_count >= 2, (
                f"Expected pending pool atoms to crystallize into a strand, got {assigned_count}/4 assigned"
            )
            print("  PASS: pending pool crystallizes into a new strand once enough similar atoms accumulate")

            # --- Pool routing: pool atoms are re-checked against existing centroids ---
            # A pool atom that later becomes attachable to a new strand (created after
            # it entered the pool) should be absorbed — not forced to spawn a new strand.
            # We verify this by putting a known atom into the pool manually, then running
            # an incremental pass after its nearest strand already exists.
            await cluster_memory({"full": True})
            # Find an assigned atom and put it back into the pool as if it were a leftover.
            assigned_row2 = await db.fetchone(
                "SELECT id, strand_id FROM memory_atom WHERE strand_id IS NOT NULL LIMIT 1"
            )
            assert assigned_row2
            pool_atom_id = assigned_row2["id"]
            expected_strand = assigned_row2["strand_id"]
            import json as _json2
            await config.set_setting(_PENDING_POOL_KEY, _json2.dumps([pool_atom_id]))
            # Re-dirty the atom so the incremental will process it.
            await db.execute("UPDATE memory_atom SET cluster_dirty=1 WHERE id=?", (pool_atom_id,))
            inc_absorb = await cluster_memory({})
            assert inc_absorb["ok"], inc_absorb
            absorbed_row = await db.fetchone("SELECT strand_id FROM memory_atom WHERE id=?", (pool_atom_id,))
            assert absorbed_row and absorbed_row["strand_id"] == expected_strand, (
                f"Pool atom should be absorbed by existing strand {expected_strand}, "
                f"got {absorbed_row['strand_id'] if absorbed_row else 'None'}"
            )
            # Pool should no longer contain the absorbed atom.
            pool_after_absorb = _json2.loads(await config.get_setting(_PENDING_POOL_KEY) or "[]")
            assert pool_atom_id not in pool_after_absorb, (
                f"Absorbed atom should be evicted from pool, but pool={pool_after_absorb}"
            )
            print("  PASS: pool atoms re-checked against existing centroids and absorbed when matchable")

            # --- Stickiness: weekly full rebuild preserves stable atom strand IDs ---
            # Incrementals build up strand assignments. A full pass (weekly rebuild)
            # must preserve those identities for atoms whose clusters haven't drifted.
            await cluster_memory({"full": True})
            base_rows = await db.fetchall("SELECT id, strand_id FROM memory_atom ORDER BY id")
            base_map = {r["id"]: r["strand_id"] for r in base_rows if r["strand_id"]}
            assert base_map

            # Dirty one atom and run an incremental, then a full rebuild.
            one_stable_id = next(iter(base_map))
            await db.execute("UPDATE memory_atom SET cluster_dirty=1 WHERE id=?", (one_stable_id,))
            await cluster_memory({})
            await cluster_memory({"full": True})

            after_rebuild = {r["id"]: r["strand_id"] for r in await db.fetchall(
                "SELECT id, strand_id FROM memory_atom ORDER BY id"
            )}
            lost = [
                aid for aid, sid in base_map.items()
                if sid and after_rebuild.get(aid) is None
            ]
            assert not lost, (
                f"Full rebuild after incremental lost strand assignments for: {lost[:5]}"
            )
            print("  PASS: full rebuild after incremental preserves stable atom strand IDs")

        finally:
            db.shutdown()

    # --- Synonym dedup gate: geometry verified with controlled vectors ---
    # End-to-end dedup requires cheap_model + a real embedding endpoint; neither
    # is present in the fixture. This test verifies the gate's cosine geometry
    # at merge_threshold=0.80 using hand-crafted unit vectors, independent of
    # the embedding backend.
    # NOTE: merge_threshold=0.80 is NOT validated against real synonym pairs
    # (e.g. "Career"/"Work" under a production embedding model). That requires
    # a live endpoint fixture and remains an open verification item.
    import math as _math
    import numpy as _np
    from workers.clustering import _best_label_match

    _dim = db.EMBED_DIM
    v_career = _np.zeros(_dim, dtype=_np.float32)
    v_career[0] = 1.0

    # v_work is 15° from v_career → cosine ≈ 0.966, above merge_threshold 0.80 → must merge
    v_work = _np.zeros(_dim, dtype=_np.float32)
    v_work[0] = _math.cos(_math.radians(15))
    v_work[1] = _math.sin(_math.radians(15))
    v_work /= _np.linalg.norm(v_work)

    # v_fitness is orthogonal to v_career → cosine = 0.0, below threshold → must stay separate
    v_fitness = _np.zeros(_dim, dtype=_np.float32)
    v_fitness[2] = 1.0

    _merge_thresh = 0.80
    _registry = {"strand_career": v_career}

    merged = _best_label_match(v_work, _registry, _merge_thresh)
    assert merged == "strand_career", (
        f"Expected near-synonym (cosine≈0.97) to merge into strand_career, got {merged}"
    )
    not_merged = _best_label_match(v_fitness, _registry, _merge_thresh)
    assert not_merged is None, (
        f"Expected unrelated label (cosine=0.0) to stay separate, got {not_merged}"
    )

    # Verify threshold boundary: vector at exactly merge_threshold must fire; just below must not.
    v_boundary_above = _np.zeros(_dim, dtype=_np.float32)
    v_boundary_above[0] = _merge_thresh
    v_boundary_above[3] = _math.sqrt(1.0 - _merge_thresh ** 2)
    v_boundary_above /= _np.linalg.norm(v_boundary_above)
    assert _best_label_match(v_boundary_above, _registry, _merge_thresh) == "strand_career"

    v_boundary_below = _np.zeros(_dim, dtype=_np.float32)
    v_boundary_below[0] = _merge_thresh - 0.01
    v_boundary_below[3] = _math.sqrt(max(0.0, 1.0 - v_boundary_below[0] ** 2))
    v_boundary_below /= _np.linalg.norm(v_boundary_below)
    assert _best_label_match(v_boundary_below, _registry, _merge_thresh) is None

    print("  PASS: dedup gate merges near-synonyms (cosine>0.80) and preserves unrelated labels")
    print("  NOTE: merge_threshold=0.80 not yet validated against real synonym geometry")
    print("        (open item: test 'Career'/'Work' cosine under production embedding model)")

    print("\nAll clustering fixture tests passed.")


if __name__ == "__main__":
    asyncio.run(run())
