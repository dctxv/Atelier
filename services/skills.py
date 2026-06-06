"""Skills repository. Enabled skills are injected into the chat system prompt."""
from __future__ import annotations

import uuid

from . import db

_FIELDS = ("name", "description", "prompt", "category", "icon", "enabled")


def _row(r: dict) -> dict:
    return {
        "id": r["id"], "name": r["name"], "description": r["description"], "prompt": r["prompt"],
        "category": r["category"], "icon": r["icon"], "enabled": bool(r["enabled"]),
        "created_at": r["created_at"], "updated_at": r["updated_at"],
    }


async def list_skills() -> list[dict]:
    rows = await db.fetchall("SELECT * FROM skill ORDER BY created_at")
    return [_row(r) for r in rows]


async def enabled_skills() -> list[dict]:
    rows = await db.fetchall("SELECT * FROM skill WHERE enabled=1")
    return [_row(r) for r in rows]


async def create(data: dict) -> dict:
    sid = str(uuid.uuid4())
    ts = db.now()
    await db.execute(
        "INSERT INTO skill(id, name, description, prompt, category, icon, enabled, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (sid, (data.get("name") or "").strip(), data.get("description", ""), data.get("prompt", ""),
         data.get("category", "general"), data.get("icon", "tasks"),
         int(bool(data.get("enabled", True))), ts, ts),
    )
    r = await db.fetchone("SELECT * FROM skill WHERE id=?", (sid,))
    return _row(r)


async def update(skill_id: str, data: dict) -> dict | None:
    existing = await db.fetchone("SELECT * FROM skill WHERE id=?", (skill_id,))
    if not existing:
        return None
    merged = {}
    for f in _FIELDS:
        if f in data:
            merged[f] = int(bool(data[f])) if f == "enabled" else data[f]
        else:
            merged[f] = existing[f]
    await db.execute(
        "UPDATE skill SET name=?, description=?, prompt=?, category=?, icon=?, enabled=?, updated_at=? WHERE id=?",
        (merged["name"], merged["description"], merged["prompt"], merged["category"],
         merged["icon"], merged["enabled"], db.now(), skill_id),
    )
    r = await db.fetchone("SELECT * FROM skill WHERE id=?", (skill_id,))
    return _row(r)


async def toggle(skill_id: str) -> bool | None:
    existing = await db.fetchone("SELECT enabled FROM skill WHERE id=?", (skill_id,))
    if not existing:
        return None
    new_val = 0 if existing["enabled"] else 1
    await db.execute("UPDATE skill SET enabled=?, updated_at=? WHERE id=?", (new_val, db.now(), skill_id))
    return bool(new_val)


async def delete(skill_id: str) -> bool:
    existing = await db.fetchone("SELECT id FROM skill WHERE id=?", (skill_id,))
    if not existing:
        return False
    await db.execute("DELETE FROM skill WHERE id=?", (skill_id,))
    return True
