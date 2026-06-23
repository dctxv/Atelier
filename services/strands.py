"""Emergent memory strand registry.

Strands are rebuildable labels over geometry-derived atom clusters. The
registry is persistent so strand ids and labels stay stable across passes, but
it owns no memory truth: atom text, confidence, provenance, and vectors remain
in the memory tables. NULL memory_atom.strand_id is the honest noise/unassigned
state surfaced to the UI as "Unsorted".
"""
from __future__ import annotations

import hashlib
import re
import uuid

import numpy as np

from . import db, embeddings, memory

_PALETTE = (
    "#6E7E8A",  # slate
    "#7C8A6E",  # sage
    "#A8756B",  # clay
    "#8A7A5A",  # brass
    "#9A6B6B",  # muted rose-brown
    "#7E6E8A",  # muted violet
    "#6F867F",  # green-blue
    "#8A7065",  # umber
)


def _vec_blob(vec: np.ndarray | list[float] | None) -> bytes | None:
    if vec is None:
        return None
    arr = np.asarray(vec, dtype=np.float32)
    if arr.shape[0] != db.EMBED_DIM:
        return None
    return arr.tobytes()


def blob_to_vec(blob) -> np.ndarray | None:
    if not blob:
        return None
    arr = np.frombuffer(bytes(blob), dtype=np.float32)
    if arr.shape[0] != db.EMBED_DIM:
        return None
    return arr.astype(np.float32, copy=True)


def _color_for_id(strand_id: str) -> str:
    h = int(hashlib.sha256(strand_id.encode()).hexdigest()[:8], 16)
    return _PALETTE[h % len(_PALETTE)]


def stable_cluster_id(atom_ids: list[str]) -> str:
    sig = "\n".join(sorted(atom_ids))
    return "strand_" + hashlib.sha256(sig.encode()).hexdigest()[:16]


def _shape(row: dict) -> dict:
    label = row.get("label")
    return {
        "id": row["id"],
        "label": label,
        "name": label or "Unlabeled strand",
        "kind": "emergent",
        "atom_count": row.get("atom_count") or 0,
        "status": row.get("status") or "active",
        "merged_into": row.get("merged_into"),
        "color": row.get("color") or _color_for_id(row["id"]),
        "glyph": row.get("glyph"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


async def load_registry(include_dormant: bool = False) -> list[dict]:
    where = "" if include_dormant else "WHERE status='active'"
    rows = await db.fetchall(
        f"SELECT * FROM memory_strands {where} ORDER BY atom_count DESC, label IS NULL, label, id"
    )
    return [_shape(r) for r in rows]


async def save_registry(strands: list[dict]) -> None:
    """Compatibility shim for old rename flows.

    The legacy registry was a JSON blob. New callers should update rows
    directly, but this preserves the old API by applying label/status edits for
    rows that already exist.
    """
    ts = db.now()

    def op(conn):
        for s in strands or []:
            sid = s.get("id")
            if not sid:
                continue
            label = s.get("label", s.get("name"))
            conn.execute(
                "UPDATE memory_strands SET label=?, updated_at=? WHERE id=?",
                (label, ts, sid),
            )

    await db.write(op)


async def strand_bootstrap() -> None:
    """No-op cold start.

    The old static career/places/etc. taxonomy is intentionally not seeded into
    the emergent registry.
    """
    return None


async def add_strand(name: str, predicates: list[str] | None = None) -> dict:
    """Create a user-named strand without predicate-bundle membership.

    The predicates argument is accepted for compatibility with old
    insight_offer resolution, but it no longer claims atoms.
    """
    label = (name or "").strip() or "Unlabeled strand"
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or "strand"
    sid = f"user_{slug}"
    existing_ids = {r["id"] for r in await load_registry(include_dormant=True)}
    if sid in existing_ids:
        sid = f"{sid}_{uuid.uuid4().hex[:8]}"
    label_vec = np.asarray(await embeddings.embed(label), dtype=np.float32)
    await upsert_strand(
        sid,
        label=label,
        label_embedding=label_vec,
        centroid=None,
        atom_count=0,
        status="active",
    )
    return (await get_strand(sid)) or {"id": sid, "name": label, "label": label}


async def get_strand(strand_id: str) -> dict | None:
    row = await db.fetchone("SELECT * FROM memory_strands WHERE id=?", (strand_id,))
    return _shape(row) if row else None


async def registry_vectors(include_dormant: bool = True) -> list[dict]:
    where = "WHERE status IN ('active','dormant')" if include_dormant else "WHERE status='active'"
    rows = await db.fetchall(
        f"SELECT * FROM memory_strands {where} ORDER BY id"
    )
    out: list[dict] = []
    for r in rows:
        item = _shape(r)
        item["centroid_vec"] = blob_to_vec(r.get("centroid"))
        item["label_vec"] = blob_to_vec(r.get("label_embedding"))
        out.append(item)
    return out


async def upsert_strand(
    strand_id: str,
    *,
    label: str | None,
    centroid: np.ndarray | list[float] | None,
    atom_count: int,
    status: str = "active",
    label_embedding: np.ndarray | list[float] | None = None,
    merged_into: str | None = None,
    color: str | None = None,
    glyph: str | None = None,
) -> None:
    ts = db.now()
    await db.execute(
        "INSERT INTO memory_strands("
        "id, label, label_embedding, centroid, atom_count, status, merged_into, color, glyph, created_at, updated_at"
        ") VALUES(?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET "
        "label=COALESCE(excluded.label, memory_strands.label), "
        "label_embedding=COALESCE(excluded.label_embedding, memory_strands.label_embedding), "
        "centroid=COALESCE(excluded.centroid, memory_strands.centroid), "
        "atom_count=excluded.atom_count, status=excluded.status, merged_into=excluded.merged_into, "
        "color=COALESCE(excluded.color, memory_strands.color), "
        "glyph=COALESCE(excluded.glyph, memory_strands.glyph), updated_at=excluded.updated_at",
        (
            strand_id,
            label,
            _vec_blob(label_embedding),
            _vec_blob(centroid),
            int(atom_count),
            status,
            merged_into,
            color or _color_for_id(strand_id),
            glyph,
            ts,
            ts,
        ),
    )


async def apply_clustering_result(
    strand_rows: list[dict],
    assignments: dict[str, str | None],
    clear_dirty_atom_ids: list[str],
) -> None:
    """Persist strand rows and single atom assignments in one writer pass."""
    ts = db.now()

    def op(conn):
        for s in strand_rows:
            sid = s["id"]
            conn.execute(
                "INSERT INTO memory_strands("
                "id, label, label_embedding, centroid, atom_count, status, merged_into, color, glyph, created_at, updated_at"
                ") VALUES(?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "label=COALESCE(excluded.label, memory_strands.label), "
                "label_embedding=COALESCE(excluded.label_embedding, memory_strands.label_embedding), "
                "centroid=COALESCE(excluded.centroid, memory_strands.centroid), "
                "atom_count=excluded.atom_count, status=excluded.status, merged_into=excluded.merged_into, "
                "color=COALESCE(excluded.color, memory_strands.color), "
                "glyph=COALESCE(excluded.glyph, memory_strands.glyph), updated_at=excluded.updated_at",
                (
                    sid,
                    s.get("label"),
                    _vec_blob(s.get("label_embedding")),
                    _vec_blob(s.get("centroid")),
                    int(s.get("atom_count") or 0),
                    s.get("status") or "active",
                    s.get("merged_into"),
                    s.get("color") or _color_for_id(sid),
                    s.get("glyph"),
                    ts,
                    ts,
                ),
            )

        for atom_id, strand_id in assignments.items():
            conn.execute(
                "UPDATE memory_atom SET strand_id=?, strand_assigned_at=?, cluster_dirty=0 WHERE id=?",
                (strand_id, ts if strand_id else None, atom_id),
            )

        for atom_id in clear_dirty_atom_ids:
            if atom_id in assignments:
                continue
            conn.execute(
                "UPDATE memory_atom SET "
                "cluster_dirty=0, "
                "strand_id=CASE WHEN NOT (status='active' OR status IS NULL) THEN NULL ELSE strand_id END, "
                "strand_assigned_at=CASE WHEN NOT (status='active' OR status IS NULL) THEN NULL ELSE strand_assigned_at END "
                "WHERE id=?",
                (atom_id,),
            )

    await db.write(op)


async def atoms_for_strand(
    strand_id: str,
    window: tuple[int, int] | None = None,
) -> list[dict]:
    if strand_id == "_unstranded":
        q = (
            "SELECT * FROM memory_atom WHERE strand_id IS NULL "
            "AND (status='active' OR status IS NULL) AND COALESCE(predicate,'') != 'suppressed'"
        )
        params: tuple = ()
    else:
        q = (
            "SELECT * FROM memory_atom WHERE strand_id=? "
            "AND (status='active' OR status IS NULL)"
        )
        params = (strand_id,)
    if window:
        q += " AND COALESCE(valid_from, created_at) BETWEEN ? AND ?"
        params = params + window
    q += " ORDER BY created_at DESC"
    rows = await db.fetchall(q, params)
    return [memory._row_to_atom(r) for r in rows]


async def resolve_strands(atom: dict) -> list[str]:
    sid = atom.get("strand_id")
    return [sid] if sid else []


async def propose_strand_clusters() -> None:
    """Legacy quarterly hook.

    The emergent clustering job replaces predicate proposal questions, so this
    function intentionally does nothing.
    """
    return None
