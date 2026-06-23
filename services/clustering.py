"""Deterministic kNN-graph clustering for memory strands."""
from __future__ import annotations

from collections import defaultdict

import numpy as np


def normalize_rows(matrix: np.ndarray) -> np.ndarray:
    mat = np.asarray(matrix, dtype=np.float32)
    if mat.size == 0:
        return mat.reshape((0, mat.shape[1] if mat.ndim == 2 else 0))
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (mat / norms).astype(np.float32)


def normalized_centroid(vectors: np.ndarray) -> np.ndarray | None:
    if vectors.size == 0:
        return None
    c = np.mean(vectors, axis=0).astype(np.float32)
    n = float(np.linalg.norm(c))
    if n <= 0:
        return None
    return (c / n).astype(np.float32)


def build_knn_graph(
    matrix: np.ndarray,
    ids: list[str],
    *,
    k: int,
    sim_threshold: float,
    block_size: int = 512,
) -> list[dict[int, float]]:
    """Build an undirected sparse top-k graph without full pairwise storage."""
    n = len(ids)
    if n == 0 or k <= 0:
        return [dict() for _ in ids]

    mat = normalize_rows(matrix)
    k = min(k, max(0, n - 1))
    overfetch = min(n, max(k, k * 4))
    adjacency: list[dict[int, float]] = [dict() for _ in ids]
    id_order = np.asarray(ids)

    for start in range(0, n, block_size):
        end = min(n, start + block_size)
        scores = mat[start:end] @ mat.T
        for local_i in range(end - start):
            i = start + local_i
            row = scores[local_i]
            row[i] = -np.inf
            if overfetch >= n:
                candidates = np.arange(n)
            else:
                candidates = np.argpartition(row, -overfetch)[-overfetch:]
            candidates = sorted(
                (int(j) for j in candidates if row[j] >= sim_threshold),
                key=lambda j: (-float(row[j]), str(id_order[j])),
            )[:k]
            for j in candidates:
                weight = float(row[j])
                if weight < sim_threshold:
                    continue
                prev = adjacency[i].get(j, -1.0)
                if weight > prev:
                    adjacency[i][j] = weight
                    adjacency[j][i] = weight

    return adjacency


def deterministic_label_propagation(
    adjacency: list[dict[int, float]],
    ids: list[str],
    *,
    max_iter: int = 20,
) -> dict[int, str]:
    """Seeded-by-order label propagation with deterministic tie breaks."""
    order = sorted(range(len(ids)), key=lambda i: ids[i])
    labels: dict[int, str] = {i: ids[i] for i in range(len(ids))}

    for _ in range(max_iter):
        changed = False
        for i in order:
            if not adjacency[i]:
                continue
            votes: dict[str, float] = defaultdict(float)
            for j, weight in adjacency[i].items():
                votes[labels[j]] += weight
            if not votes:
                continue
            best_label, _ = sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))[0]
            if best_label != labels[i]:
                labels[i] = best_label
                changed = True
        if not changed:
            break
    return labels


def communities(
    matrix: np.ndarray,
    ids: list[str],
    *,
    k: int,
    sim_threshold: float,
    min_cluster_size: int,
    block_size: int = 512,
    max_iter: int = 20,
) -> tuple[list[list[int]], set[int]]:
    adjacency = build_knn_graph(
        matrix,
        ids,
        k=k,
        sim_threshold=sim_threshold,
        block_size=block_size,
    )
    labels = deterministic_label_propagation(adjacency, ids, max_iter=max_iter)
    grouped: dict[str, list[int]] = defaultdict(list)
    for i, label in labels.items():
        grouped[label].append(i)

    clusters: list[list[int]] = []
    noise: set[int] = set()
    for members in grouped.values():
        members = sorted(members, key=lambda i: ids[i])
        if len(members) < min_cluster_size:
            noise.update(members)
        else:
            clusters.append(members)

    clusters.sort(key=lambda members: ids[members[0]])
    return clusters, noise
