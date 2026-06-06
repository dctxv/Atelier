"""File storage repository + share-link logic (Part 2.6).

Shares are expiring tokens over existing uploaded files. The public download
route validates expiry + count and streams through the validating handler — raw
paths are never exposed.
"""
from __future__ import annotations

import secrets
import uuid
from pathlib import Path

from . import db

UPLOADS_DIR = Path("data") / "uploads"


def _file_row(r: dict) -> dict:
    return {k: r[k] for k in ("id", "name", "stored_name", "size", "type", "created_at")}


async def list_files() -> list[dict]:
    rows = await db.fetchall("SELECT * FROM file ORDER BY created_at DESC")
    return [_file_row(r) for r in rows]


async def get(file_id: str) -> dict | None:
    r = await db.fetchone("SELECT * FROM file WHERE id=?", (file_id,))
    return _file_row(r) if r else None


async def create(name: str, stored_name: str, size: int, mime: str) -> dict:
    fid = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO file(id, name, stored_name, size, type, created_at) VALUES(?,?,?,?,?,?)",
        (fid, name, stored_name, size, mime, db.now()),
    )
    return await get(fid)


async def delete(file_id: str) -> dict | None:
    target = await get(file_id)
    if not target:
        return None
    await db.execute("DELETE FROM file WHERE id=?", (file_id,))
    await db.execute("DELETE FROM share WHERE file_id=?", (file_id,))
    return target


# ── Shares ────────────────────────────────────────────────────────────────────

async def create_share(file_id: str, expires_at: int | None, max_downloads: int | None) -> dict | None:
    if not await get(file_id):
        return None
    sid = str(uuid.uuid4())
    token = secrets.token_urlsafe(32)
    await db.execute(
        "INSERT INTO share(id, file_id, token, expires_at, max_downloads, downloads, created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (sid, file_id, token, expires_at, max_downloads, 0, db.now()),
    )
    return {
        "id": sid, "file_id": file_id, "token": token,
        "expires_at": expires_at, "max_downloads": max_downloads, "downloads": 0,
    }


async def list_shares(file_id: str | None = None) -> list[dict]:
    if file_id:
        rows = await db.fetchall("SELECT * FROM share WHERE file_id=? ORDER BY created_at DESC", (file_id,))
    else:
        rows = await db.fetchall("SELECT * FROM share ORDER BY created_at DESC")
    return rows


async def revoke_share(share_id: str) -> bool:
    existing = await db.fetchone("SELECT id FROM share WHERE id=?", (share_id,))
    if not existing:
        return False
    await db.execute("DELETE FROM share WHERE id=?", (share_id,))
    return True


async def resolve_share(token: str) -> dict | None:
    return await db.fetchone("SELECT * FROM share WHERE token=?", (token,))


async def record_access_and_increment(share: dict, ip: str):
    """Log an access and bump the download counter (single writer = atomic)."""
    def op(conn):
        conn.execute(
            "INSERT INTO share_access(id, share_id, ip, accessed_at) VALUES(?,?,?,?)",
            (str(uuid.uuid4()), share["id"], ip, db.now()),
        )
        conn.execute("UPDATE share SET downloads = downloads + 1 WHERE id=?", (share["id"],))

    await db.write(op)


async def recent_access_count(share_id: str, window_seconds: int) -> int:
    cutoff = db.now() - window_seconds
    row = await db.fetchone(
        "SELECT COUNT(*) AS n FROM share_access WHERE share_id=? AND accessed_at>=?",
        (share_id, cutoff),
    )
    return row["n"] if row else 0
