"""Email triage backend (Part 2.7).

  - Accounts store IMAP/SMTP creds encrypted (services.crypto). No plaintext.
  - IMAP sync and SMTP send are blocking stdlib calls, so they run in threads
    (asyncio.to_thread) and never block the event loop.
  - Categorization uses embeddings + the cheap model (in workers/email.py).
  - EXPLICIT SEND ONLY: the server never sends autonomously. send_draft() exists
    but is only ever called by the explicit /send endpoint action.

Prefer OAuth for Gmail and an app-specific password for iCloud — in v1 we accept
an app password / token via the encrypted creds blob.
"""
from __future__ import annotations

import email
import imaplib
import json
import smtplib
import uuid
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parsedate_to_datetime

from . import crypto, db


def _decode(value) -> str:
    try:
        return str(make_header(decode_header(value or "")))
    except Exception:
        return value or ""


# ── Accounts ──────────────────────────────────────────────────────────────────

async def add_account(address: str, creds: dict, protocol: str = "imap") -> dict:
    aid = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO mail_account(id, address, protocol, creds_enc, created_at) VALUES(?,?,?,?,?)",
        (aid, address, protocol, crypto.encrypt(json.dumps(creds)), db.now()),
    )
    return {"id": aid, "address": address, "protocol": protocol}


async def list_accounts() -> list[dict]:
    rows = await db.fetchall("SELECT id, address, protocol, created_at FROM mail_account ORDER BY created_at")
    return rows


async def _account_creds(account_id: str) -> tuple[dict, dict] | None:
    row = await db.fetchone("SELECT * FROM mail_account WHERE id=?", (account_id,))
    if not row:
        return None
    return row, json.loads(crypto.decrypt(row["creds_enc"]))


async def delete_account(account_id: str) -> bool:
    existing = await db.fetchone("SELECT id FROM mail_account WHERE id=?", (account_id,))
    if not existing:
        return False

    def op(conn):
        conn.execute("DELETE FROM mail_message WHERE account_id=?", (account_id,))
        conn.execute("DELETE FROM mail_account WHERE id=?", (account_id,))

    await db.write(op)
    return True


# ── IMAP sync (blocking; called via to_thread) ────────────────────────────────

def _fetch_imap(creds: dict, limit: int) -> list[dict]:
    host = creds["imap_host"]
    port = int(creds.get("imap_port", 993))
    M = imaplib.IMAP4_SSL(host, port)
    try:
        M.login(creds["username"], creds["password"])
        M.select("INBOX", readonly=True)
        typ, data = M.search(None, "ALL")
        ids = data[0].split()
        ids = ids[-limit:] if limit else ids
        out = []
        for num in reversed(ids):
            typ, msg_data = M.fetch(num, "(UID RFC822.HEADER BODY.PEEK[TEXT]<0.2048>)")
            uid = None
            header_bytes = b""
            body_text = ""
            for part in msg_data:
                if isinstance(part, tuple):
                    meta = part[0].decode(errors="ignore")
                    if "UID" in meta:
                        import re as _re
                        m = _re.search(r"UID (\d+)", meta)
                        if m:
                            uid = m.group(1)
                    if "HEADER" in meta:
                        header_bytes = part[1]
                    elif "TEXT" in meta or "BODY" in meta:
                        body_text = part[1].decode(errors="ignore")
            msg = email.message_from_bytes(header_bytes)
            out.append({
                "uid": uid or num.decode(),
                "from_addr": _decode(msg.get("From")),
                "subject": _decode(msg.get("Subject")),
                "snippet": " ".join(body_text.split())[:280],
                "received_at": _parse_date(msg.get("Date")),
            })
        return out
    finally:
        try:
            M.logout()
        except Exception:
            pass


def _parse_date(date_str) -> int:
    try:
        return int(parsedate_to_datetime(date_str).timestamp())
    except Exception:
        return db.now()


async def sync_account(account_id: str, limit: int = 50) -> list[str]:
    """Fetch recent messages, upsert by uid. Returns ids of NEW messages."""
    pair = await _account_creds(account_id)
    if not pair:
        return []
    _row, creds = pair
    import asyncio
    fetched = await asyncio.to_thread(_fetch_imap, creds, limit)

    new_ids = []
    for m in fetched:
        existing = await db.fetchone(
            "SELECT id FROM mail_message WHERE account_id=? AND uid=?", (account_id, m["uid"])
        )
        if existing:
            continue
        mid = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO mail_message(id, account_id, uid, from_addr, subject, snippet, received_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (mid, account_id, m["uid"], m["from_addr"], m["subject"], m["snippet"], m["received_at"]),
        )
        new_ids.append(mid)
    return new_ids


# ── Messages ──────────────────────────────────────────────────────────────────

async def list_messages(account_id: str | None = None, limit: int = 100) -> list[dict]:
    if account_id:
        return await db.fetchall(
            "SELECT * FROM mail_message WHERE account_id=? ORDER BY received_at DESC LIMIT ?",
            (account_id, limit),
        )
    return await db.fetchall("SELECT * FROM mail_message ORDER BY received_at DESC LIMIT ?", (limit,))


async def get_message(message_id: str) -> dict | None:
    return await db.fetchone("SELECT * FROM mail_message WHERE id=?", (message_id,))


async def set_category(message_id: str, category: str, reason: str):
    await db.execute(
        "UPDATE mail_message SET category=?, category_reason=? WHERE id=?",
        (category, reason, message_id),
    )


async def uncategorized(limit: int = 50) -> list[dict]:
    return await db.fetchall(
        "SELECT * FROM mail_message WHERE category IS NULL ORDER BY received_at DESC LIMIT ?", (limit,)
    )


# ── Drafts ────────────────────────────────────────────────────────────────────

async def save_draft(in_reply_to: str, body: str) -> dict:
    did = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO mail_draft(id, in_reply_to, body, created_at) VALUES(?,?,?,?)",
        (did, in_reply_to, body, db.now()),
    )
    return {"id": did, "in_reply_to": in_reply_to, "body": body}


async def get_draft(draft_id: str) -> dict | None:
    return await db.fetchone("SELECT * FROM mail_draft WHERE id=?", (draft_id,))


def _send_smtp(creds: dict, to_addr: str, subject: str, body: str):
    msg = EmailMessage()
    msg["From"] = creds["username"]
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    host = creds.get("smtp_host")
    port = int(creds.get("smtp_port", 465))
    with smtplib.SMTP_SSL(host, port) as s:
        s.login(creds["username"], creds["password"])
        s.send_message(msg)


async def send_draft(draft_id: str, account_id: str, to_addr: str, subject: str) -> bool:
    """EXPLICIT send only. Called from the /send endpoint, never autonomously."""
    draft = await get_draft(draft_id)
    if not draft:
        return False
    pair = await _account_creds(account_id)
    if not pair:
        return False
    _row, creds = pair
    import asyncio
    await asyncio.to_thread(_send_smtp, creds, to_addr, subject, draft["body"])
    await db.execute("UPDATE mail_draft SET sent_at=? WHERE id=?", (db.now(), draft_id))
    return True
