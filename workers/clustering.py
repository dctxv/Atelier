"""Emergent memory clustering worker.

The worker derives strand structure from existing atom embeddings. It never runs
on the chat reply path, never calls the active model, and writes only strand
bookkeeping columns.
"""
from __future__ import annotations

import json
import time

import numpy as np

from services import clustering as cluster_core
from services import config, db, embeddings, llm, retrieval, strands
from . import jobs

_VERSION_KEY = "cluster.last_knn_version"
_PENDING_POOL_KEY = "cluster.pending_pool"


async def _cfg(key: str, default):
    val = await config.get_setting(key)
    if val is None:
        return default
    try:
        if isinstance(default, bool):
            return str(val).lower() in ("1", "true", "yes", "on")
        return type(default)(val)
    except Exception:
        return default


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


def _version_json(version: tuple[int, int, int]) -> str:
    return json.dumps(list(version), separators=(",", ":"))


def _clean_label(raw: str) -> str | None:
    label = (raw or "").strip().strip("\"'`")
    label = " ".join(label.split())
    if not label:
        return None
    if len(label) > 48:
        label = label[:48].rsplit(" ", 1)[0].strip() or label[:48].strip()
    return label


async def _using_real_embeddings() -> bool:
    """Return True when a configured real embedding model is active (not hash fallback).

    The dedup gate (_best_label_match) is cosine-based. Under the local hash
    fallback 'Career' and 'Work' produce near-orthogonal vectors, so the gate
    silently no-ops and duplicates slip through. Only engage it when we know
    the embedding space is semantically meaningful.
    """
    return bool(await config.get_setting("embedding_model"))


async def _load_pending_pool(active_id_set: set[str]) -> list[str]:
    """Load the cross-pass leftover pool, filtering out atoms no longer active."""
    raw = await config.get_setting(_PENDING_POOL_KEY)
    if not raw:
        return []
    try:
        pool = json.loads(raw)
    except Exception:
        return []
    return [aid for aid in pool if isinstance(aid, str) and aid in active_id_set]


async def _save_pending_pool(pool: list[str]) -> None:
    await config.set_setting(_PENDING_POOL_KEY, json.dumps(pool))


async def _label_clusters(
    cluster_items: list[dict],
    id_to_text: dict[str, str],
    matrix: np.ndarray,
    ids: list[str],
    sample_size: int,
) -> dict[str, str]:
    if not cluster_items:
        return {}
    if not await config.get_setting("cheap_model"):
        return {}

    id_to_index = {aid: i for i, aid in enumerate(ids)}
    blocks: list[str] = []
    for item in cluster_items:
        centroid = item.get("centroid")
        member_ids = item.get("member_ids") or []
        if centroid is None:
            continue
        scored = []
        for aid in member_ids:
            idx = id_to_index.get(aid)
            if idx is None:
                continue
            scored.append((float(matrix[idx] @ centroid), aid))
        reps = [
            id_to_text[aid]
            for _, aid in sorted(scored, key=lambda pair: (-pair[0], pair[1]))[:sample_size]
            if aid in id_to_text
        ]
        if reps:
            lines = "\n".join(f"- {text}" for text in reps)
            blocks.append(f"{item['key']}:\n{lines}")

    if not blocks:
        return {}

    prompt = (
        "Name each memory cluster with a short, concrete noun phrase. "
        "Use 2-6 words. Do not use generic labels like Misc, Work, Life, or Other. "
        "Return only a JSON object whose keys are the cluster ids and values are labels.\n\n"
        + "\n\n".join(blocks)
    )
    try:
        raw = await llm.cheap_strict(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=300,
            task="strand_cluster",
        )
    except Exception:
        return {}

    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        data = json.loads(raw[start:end + 1])
    except Exception:
        return {}
    return {str(k): label for k, v in data.items() if (label := _clean_label(str(v)))}


async def _embed_label(label: str | None) -> np.ndarray | None:
    if not label:
        return None
    return np.asarray(await embeddings.embed(label), dtype=np.float32)


def _best_existing_centroid(
    centroid: np.ndarray,
    existing: list[dict],
    threshold: float,
    used: set[str],
) -> str | None:
    candidates = []
    for s in existing:
        if s["id"] in used:
            continue
        vec = s.get("centroid_vec")
        if vec is None:
            continue
        sim = float(vec @ centroid)
        if sim >= threshold:
            candidates.append((sim, s["id"]))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (-item[0], item[1]))[0][1]


def _best_label_match(
    label_vec: np.ndarray,
    label_registry: dict[str, np.ndarray],
    threshold: float,
) -> str | None:
    candidates = []
    for sid, vec in label_registry.items():
        sim = float(vec @ label_vec)
        if sim >= threshold:
            candidates.append((sim, sid))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (-item[0], item[1]))[0][1]


async def _clusters_to_assignments(
    cluster_member_ids: list[list[str]],
    matrix: np.ndarray,
    ids: list[str],
    existing: list[dict],
    id_to_text: dict[str, str],
    *,
    sample_size: int,
    drift_threshold: float,
    merge_threshold: float,
    real_embeddings: bool = True,
) -> tuple[dict[str, str], dict[str, dict]]:
    id_to_index = {aid: i for i, aid in enumerate(ids)}
    existing_by_id = {s["id"]: s for s in existing}
    match_threshold = max(0.0, min(1.0, 1.0 - drift_threshold))
    label_registry: dict[str, np.ndarray] = {
        s["id"]: s["label_vec"]
        for s in existing
        if s.get("label_vec") is not None and s.get("status") != "merged"
    }

    cluster_items: list[dict] = []
    for member_ids in cluster_member_ids:
        member_indices = [id_to_index[aid] for aid in member_ids if aid in id_to_index]
        centroid = cluster_core.normalized_centroid(matrix[member_indices])
        if centroid is None:
            continue
        cluster_items.append({
            "key": strands.stable_cluster_id(member_ids),
            "member_ids": member_ids,
            "centroid": centroid,
        })

    labels = await _label_clusters(cluster_items, id_to_text, matrix, ids, sample_size)

    used_centroid_matches: set[str] = set()
    assignments: dict[str, str] = {}
    target_info: dict[str, dict] = {}

    for item in sorted(cluster_items, key=lambda c: c["key"]):
        member_ids = item["member_ids"]
        centroid = item["centroid"]
        sid = _best_existing_centroid(centroid, existing, match_threshold, used_centroid_matches)
        label = None
        label_vec = None

        if sid:
            used_centroid_matches.add(sid)
            existing_row = existing_by_id.get(sid, {})
            label = existing_row.get("label")
            label_vec = existing_row.get("label_vec")

        if not sid:
            candidate = labels.get(item["key"])
            if candidate:
                candidate_vec = await _embed_label(candidate)
                # Only run the synonym dedup gate when using a semantically
                # meaningful embedding model. Under the local hash fallback,
                # cosine("Career", "Work") ≈ 0, making the gate completely inert
                # and producing silent duplicates instead of merges.
                if candidate_vec is not None and real_embeddings:
                    merged = _best_label_match(candidate_vec, label_registry, merge_threshold)
                else:
                    merged = None
                if merged:
                    sid = merged
                    existing_row = existing_by_id.get(sid, {})
                    label = existing_row.get("label")
                    label_vec = existing_row.get("label_vec")
                else:
                    sid = item["key"]
                    label = candidate
                    label_vec = candidate_vec
                    if candidate_vec is not None and real_embeddings:
                        label_registry[sid] = candidate_vec
            else:
                sid = item["key"]

        info = target_info.setdefault(sid, {
            "id": sid,
            "label": label,
            "label_embedding": label_vec,
            "member_ids": [],
        })
        if not info.get("label") and label:
            info["label"] = label
        if info.get("label_embedding") is None and label_vec is not None:
            info["label_embedding"] = label_vec
        info["member_ids"].extend(member_ids)

        for aid in member_ids:
            assignments[aid] = sid

    return assignments, target_info


async def _active_rows() -> list[dict]:
    return await db.fetchall(
        "SELECT id, text, strand_id FROM memory_atom "
        "WHERE (status='active' OR status IS NULL) "
        "AND COALESCE(predicate,'') != 'suppressed' "
        "ORDER BY id"
    )


async def _dirty_ids() -> list[str]:
    rows = await db.fetchall("SELECT id FROM memory_atom WHERE cluster_dirty=1 ORDER BY id")
    return [r["id"] for r in rows]


async def _stale_strand_ids() -> list[str]:
    """Atoms that left the active set but still point to a strand.

    These are suppressed or non-active-status atoms whose strand_id was never
    cleared. They need to be nulled out so dormant strand atom_counts stay
    accurate and Unsorted counts are correct.
    """
    rows = await db.fetchall(
        "SELECT id FROM memory_atom "
        "WHERE strand_id IS NOT NULL "
        "AND (status NOT IN ('active') AND status IS NOT NULL "
        "     OR COALESCE(predicate,'') = 'suppressed')"
    )
    return [r["id"] for r in rows]


def _strand_rows_from_members(
    target_members: dict[str, list[str]],
    matrix: np.ndarray,
    ids: list[str],
    target_info: dict[str, dict],
    existing: list[dict],
) -> list[dict]:
    id_to_index = {aid: i for i, aid in enumerate(ids)}
    existing_by_id = {s["id"]: s for s in existing}
    rows: list[dict] = []
    active_ids = set(target_members)

    for sid, member_ids in sorted(target_members.items()):
        member_indices = [id_to_index[aid] for aid in member_ids if aid in id_to_index]
        centroid = cluster_core.normalized_centroid(matrix[member_indices])
        old = existing_by_id.get(sid, {})
        info = target_info.get(sid, {})
        rows.append({
            "id": sid,
            "label": info.get("label", old.get("label")),
            "label_embedding": info.get("label_embedding", old.get("label_vec")),
            "centroid": centroid,
            "atom_count": len(member_ids),
            "status": "active",
            "color": old.get("color"),
            "glyph": old.get("glyph"),
        })

    for s in existing:
        if s["id"] not in active_ids and s.get("status") != "merged":
            rows.append({
                "id": s["id"],
                "label": s.get("label"),
                "label_embedding": s.get("label_vec"),
                "centroid": s.get("centroid_vec"),
                "atom_count": 0,
                "status": "dormant",
                "color": s.get("color"),
                "glyph": s.get("glyph"),
            })
    return rows


@jobs.register("cluster_memory")
async def cluster_memory(payload: dict | None = None):
    payload = payload or {}
    started = time.perf_counter()
    max_runtime_ms = await _cfg("cluster.max_runtime_ms", 2000)  # [VALIDATE]
    knn_k = await _cfg("cluster.knn_k", 15)  # [VALIDATE]
    sim_threshold = await _cfg("cluster.sim_threshold", 0.55)  # [VALIDATE]
    min_cluster_size = await _cfg("cluster.min_cluster_size", 4)  # [VALIDATE]
    drift_threshold = await _cfg("cluster.drift_threshold", 0.15)  # [VALIDATE]
    merge_threshold = await _cfg("label.merge_threshold", 0.80)  # [VALIDATE]
    sample_size = await _cfg("label.sample_size", 6)  # [VALIDATE]
    block_size = await _cfg("cluster.block_size", 512)
    max_iter = await _cfg("cluster.max_iter", 20)

    force_full = bool(payload.get("full") or payload.get("backfill"))
    dirty_ids = await _dirty_ids()

    # Check version before the ~51 MB matrix copy to skip clean hourly runs cheaply.
    snapshot_meta = await retrieval.memory_knn_snapshot(copy=False)
    version = tuple(snapshot_meta["version"])
    last_version = await config.get_setting(_VERSION_KEY)

    if not force_full and not dirty_ids and last_version == _version_json(version):
        return {"ok": True, "noop": "clean"}

    snapshot = await retrieval.memory_knn_snapshot(copy=True)
    active_rows = await _active_rows()
    real_embeddings = await _using_real_embeddings()

    if not active_rows:
        await strands.apply_clustering_result([], {}, dirty_ids)
        await config.set_setting(_VERSION_KEY, _version_json(version))
        return {"ok": True, "active_atoms": 0}

    matrix_all = cluster_core.normalize_rows(snapshot["matrix"])
    snapshot_ids = list(snapshot["ids"])
    snapshot_index = {aid: i for i, aid in enumerate(snapshot_ids)}
    active_ids = [r["id"] for r in active_rows if r["id"] in snapshot_index]
    if not active_ids:
        await strands.apply_clustering_result([], {}, dirty_ids)
        return {"ok": True, "active_atoms": 0}

    active_indices = [snapshot_index[aid] for aid in active_ids]
    active_index = {aid: i for i, aid in enumerate(active_ids)}
    matrix = matrix_all[active_indices]
    id_to_text = {r["id"]: r["text"] for r in active_rows}
    existing = await strands.registry_vectors(include_dormant=True)
    has_active_centroids = any(s.get("status") == "active" and s.get("centroid_vec") is not None for s in existing)
    full_pass = force_full or not has_active_centroids

    if _elapsed_ms(started) > max_runtime_ms:
        return {"ok": False, "skipped": "max_runtime_before_compute"}

    assignments: dict[str, str | None] = {}
    target_info: dict[str, dict] = {}

    if full_pass:
        cluster_indices, noise = cluster_core.communities(
            matrix,
            active_ids,
            k=knn_k,
            sim_threshold=sim_threshold,
            min_cluster_size=min_cluster_size,
            block_size=block_size,
            max_iter=max_iter,
        )
        cluster_member_ids = [[active_ids[i] for i in members] for members in cluster_indices]
        cluster_assignments, target_info = await _clusters_to_assignments(
            cluster_member_ids,
            matrix,
            active_ids,
            existing,
            id_to_text,
            sample_size=sample_size,
            drift_threshold=drift_threshold,
            merge_threshold=merge_threshold,
            real_embeddings=real_embeddings,
        )
        assignments.update(cluster_assignments)
        for i in noise:
            assignments[active_ids[i]] = None
        # Full pass resets the pending pool — all atoms have been reconsidered.
        await _save_pending_pool([])
    else:
        dirty_active = [aid for aid in dirty_ids if aid in active_index]
        existing_active = [
            s for s in existing
            if s.get("status") == "active" and s.get("centroid_vec") is not None
        ]
        leftovers: list[str] = []
        for aid in dirty_active:
            vec = matrix[active_index[aid]]
            candidates = []
            for s in existing_active:
                sim = float(vec @ s["centroid_vec"])
                if sim >= sim_threshold:
                    candidates.append((sim, s["id"]))
            if candidates:
                assignments[aid] = sorted(candidates, key=lambda item: (-item[0], item[1]))[0][1]
            else:
                leftovers.append(aid)

        # Carry-over pending pool: accumulate leftovers across passes so that
        # new strands can crystallize even when fewer than min_cluster_size
        # similar atoms arrive in a single hourly window.
        active_id_set = set(active_ids)
        pending_pool = await _load_pending_pool(active_id_set)
        # Atoms being re-processed this pass leave the stable pool; they'll
        # re-join as leftovers below if they still don't match anything.
        dirty_set = set(dirty_active)
        pool_stable = [aid for aid in pending_pool if aid not in dirty_set]
        combined = list(dict.fromkeys(pool_stable + leftovers))

        if len(combined) >= min_cluster_size:
            combined_indices = [active_index[aid] for aid in combined]
            local_matrix = matrix[combined_indices]
            local_clusters, local_noise = cluster_core.communities(
                local_matrix,
                combined,
                k=knn_k,
                sim_threshold=sim_threshold,
                min_cluster_size=min_cluster_size,
                block_size=block_size,
                max_iter=max_iter,
            )
            cluster_member_ids = [[combined[i] for i in members] for members in local_clusters]
            cluster_assignments, target_info = await _clusters_to_assignments(
                cluster_member_ids,
                matrix,
                active_ids,
                existing,
                id_to_text,
                sample_size=sample_size,
                drift_threshold=drift_threshold,
                merge_threshold=merge_threshold,
                real_embeddings=real_embeddings,
            )
            assignments.update(cluster_assignments)
            # Noise atoms from pool clustering stay unassigned; persist them
            # for the next pass so they can accumulate further.
            noise_pool = [combined[i] for i in local_noise]
            await _save_pending_pool(noise_pool)
            for i in local_noise:
                assignments[combined[i]] = None
        else:
            # Not enough to attempt clustering; keep the pool warm.
            await _save_pending_pool(combined)
            for aid in leftovers:
                assignments[aid] = None

    # Null out stale strand assignments for atoms that left the active set
    # (suppressed or non-active status). Without this, Unsorted counts are
    # understated and dormant strand atom_counts are inflated.
    stale_ids = await _stale_strand_ids()
    for aid in stale_ids:
        assignments[aid] = None

    if _elapsed_ms(started) > max_runtime_ms:
        return {"ok": False, "skipped": "max_runtime_before_write"}

    current_members: dict[str, list[str]] = {}
    for row in active_rows:
        aid = row["id"]
        sid = assignments.get(aid, row.get("strand_id"))
        if sid:
            current_members.setdefault(sid, []).append(aid)

    strand_rows = _strand_rows_from_members(current_members, matrix, active_ids, target_info, existing)
    await strands.apply_clustering_result(strand_rows, assignments, dirty_ids)
    await config.set_setting(_VERSION_KEY, _version_json(version))
    result = {
        "ok": True,
        "full": full_pass,
        "active_atoms": len(active_ids),
        "assigned": sum(1 for sid in assignments.values() if sid),
        "noise": sum(1 for sid in assignments.values() if sid is None),
        "strands": len([s for s in strand_rows if s.get("status") == "active"]),
        "duration_ms": round(_elapsed_ms(started), 2),
    }
    if not real_embeddings:
        result["labels_unreliable"] = True
    return result


def register_schedule():
    """Register hourly incremental pass and weekly full rebuild."""
    jobs.add_periodic(
        lambda: jobs.enqueue("cluster_memory"),
        seconds=3600,
        job_id="cluster_memory",
    )
    # Weekly full rebuild thaws the taxonomy: splits overgrown strands,
    # re-merges drifted ones, and re-evaluates all pending pool atoms.
    jobs.add_periodic(
        lambda: jobs.enqueue("cluster_memory", {"full": True}),
        seconds=604800,
        job_id="cluster_memory_full",
    )
