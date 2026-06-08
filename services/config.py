"""Config & endpoint registry, backed by SQLite (replaces data/config.json).

Endpoints store their API key encrypted (services.crypto). Keys are decrypted
only in-process to build request headers — they are never returned to the
client. Singleton app settings (active endpoint/model, embedding config) live
in the app_config key/value table.
"""
from __future__ import annotations

import uuid

from . import crypto, db  # noqa: F401  (crypto used by secret helpers)


def _normalize(url: str) -> str:
    url = (url or "").rstrip("/")
    if not url.endswith("/v1"):
        url += "/v1"
    return url


# ── app_config key/value ──────────────────────────────────────────────────────

async def get_setting(key: str, default=None):
    row = await db.fetchone("SELECT value FROM app_config WHERE key=?", (key,))
    return row["value"] if row else default


async def set_setting(key: str, value):
    await db.execute(
        "INSERT INTO app_config(key, value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value if value is None else str(value)),
    )


# ── Encrypted secrets (provider API keys) ─────────────────────────────────────
# Stored the same way endpoint keys are: encrypted at rest, never returned raw.

async def set_secret(name: str, value: str):
    await set_setting(f"secret:{name}", crypto.encrypt(value or ""))


async def get_secret(name: str) -> str:
    enc = await get_setting(f"secret:{name}")
    return crypto.decrypt(enc) if enc else ""


async def has_secret(name: str) -> bool:
    return bool(await get_setting(f"secret:{name}"))


# ── endpoints ─────────────────────────────────────────────────────────────────

def _public(row: dict) -> dict:
    """Shape returned to the client — never includes the key itself."""
    return {
        "id": row["id"],
        "name": row["name"],
        "url": row["base_url"],
        "type": row["type"],
        "has_key": bool(row.get("api_key_enc")),
    }


async def list_endpoints() -> list[dict]:
    rows = await db.fetchall("SELECT * FROM endpoint ORDER BY created_at")
    return [_public(r) for r in rows]


async def add_endpoint(name: str, url: str, api_key: str = "", type_: str = "local") -> dict:
    ep_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO endpoint(id, name, base_url, api_key_enc, type, created_at) "
        "VALUES(?,?,?,?,?,?)",
        (ep_id, name or "Unnamed", _normalize(url), crypto.encrypt(api_key or ""),
         type_ or "local", db.now()),
    )
    if not await get_setting("active_endpoint_id"):
        await set_setting("active_endpoint_id", ep_id)
    return await get_endpoint(ep_id)


async def get_endpoint(ep_id: str) -> dict | None:
    row = await db.fetchone("SELECT * FROM endpoint WHERE id=?", (ep_id,))
    return _public(row) if row else None


async def delete_endpoint(ep_id: str):
    await db.execute("DELETE FROM endpoint WHERE id=?", (ep_id,))
    if await get_setting("active_endpoint_id") == ep_id:
        rows = await db.fetchall("SELECT id FROM endpoint ORDER BY created_at LIMIT 1")
        await set_setting("active_endpoint_id", rows[0]["id"] if rows else None)
        await set_setting("active_model", None)


async def activate_endpoint(ep_id: str) -> bool:
    row = await db.fetchone("SELECT id FROM endpoint WHERE id=?", (ep_id,))
    if not row:
        return False
    await set_setting("active_endpoint_id", ep_id)
    await set_setting("active_model", None)
    return True


async def active_endpoint_raw() -> dict | None:
    """Internal: full row incl. decrypted key, for building request headers."""
    eid = await get_setting("active_endpoint_id")
    if not eid:
        return None
    row = await db.fetchone("SELECT * FROM endpoint WHERE id=?", (eid,))
    if not row:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "url": row["base_url"],
        "api_key": crypto.decrypt(row.get("api_key_enc") or ""),
        "type": row["type"],
    }


async def endpoint_raw(ep_id: str) -> dict | None:
    row = await db.fetchone("SELECT * FROM endpoint WHERE id=?", (ep_id,))
    if not row:
        return None
    return {
        "id": row["id"], "name": row["name"], "url": row["base_url"],
        "api_key": crypto.decrypt(row.get("api_key_enc") or ""), "type": row["type"],
    }


def headers(ep: dict) -> dict:
    h = {"Content-Type": "application/json"}
    if ep.get("api_key"):
        h["Authorization"] = f"Bearer {ep['api_key']}"
    return h


async def public_config() -> dict:
    return {
        "endpoints": await list_endpoints(),
        "active_endpoint_id": await get_setting("active_endpoint_id"),
        "active_model": await get_setting("active_model"),
        "cheap_model": await get_setting("cheap_model"),
        "system_prompt": await get_setting("system_prompt", ""),
    }
