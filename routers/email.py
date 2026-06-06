"""Email endpoints. Sync/categorize are background; send is explicit only."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from services import email as mail
from workers import email as mail_worker
from workers import jobs

router = APIRouter(prefix="/api/mail")


@router.get("/accounts")
async def list_accounts():
    return {"accounts": await mail.list_accounts()}


@router.post("/accounts")
async def add_account(request: Request):
    data = await request.json()
    required = ("address", "imap_host", "username", "password")
    if not all(data.get(k) for k in required):
        raise HTTPException(400, f"required: {required}")
    creds = {k: data[k] for k in ("imap_host", "imap_port", "username", "password",
                                  "smtp_host", "smtp_port") if k in data}
    account = await mail.add_account(data["address"], creds, data.get("protocol", "imap"))
    await jobs.enqueue("mail_sync", {"account_id": account["id"]})
    return {"ok": True, "account": account}


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: str):
    if not await mail.delete_account(account_id):
        raise HTTPException(404, "Account not found")
    return {"ok": True}


@router.post("/accounts/{account_id}/sync")
async def sync_account(account_id: str):
    await jobs.enqueue("mail_sync", {"account_id": account_id})
    return {"ok": True, "status": "queued"}


@router.get("/messages")
async def list_messages(account_id: str | None = None):
    return {"messages": await mail.list_messages(account_id)}


@router.get("/messages/{message_id}")
async def get_message(message_id: str):
    msg = await mail.get_message(message_id)
    if not msg:
        raise HTTPException(404, "Message not found")
    return {"message": msg}


@router.post("/messages/{message_id}/draft")
async def draft_reply(message_id: str):
    draft = await mail_worker.draft_reply(message_id)
    if not draft:
        raise HTTPException(404, "Message not found")
    return {"ok": True, "draft": draft}


@router.post("/messages/{message_id}/send")
async def send_reply(message_id: str, request: Request):
    """Explicit send. Never called by the server on its own."""
    data = await request.json()
    msg = await mail.get_message(message_id)
    if not msg:
        raise HTTPException(404, "Message not found")
    draft_id = data.get("draft_id")
    if not draft_id:
        raise HTTPException(400, "draft_id required")
    subject = data.get("subject") or f"Re: {msg['subject']}"
    sent = await mail.send_draft(draft_id, msg["account_id"], msg["from_addr"], subject)
    if not sent:
        raise HTTPException(400, "Could not send (draft/account missing)")
    return {"ok": True, "sent": True}
