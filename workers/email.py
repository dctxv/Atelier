"""Email background jobs (Part 2.7): sync poll + categorize.

Sync and categorize are background; drafting is on-demand (the only big-model
use in email). Sending is never a job — it only happens on an explicit user
action through the router.
"""
from __future__ import annotations

from services import email as mail
from services import llm
from . import jobs

CATEGORIES = ["important", "personal", "work", "newsletter", "promotion", "social", "spam", "other"]

_SYSTEM = (
    "Classify the email into exactly one category from this list: "
    + ", ".join(CATEGORIES) + ". "
    'Return ONLY JSON: {"category":"<one>","reason":"<short phrase>"}.'
)


@jobs.register("mail_sync")
async def mail_sync(payload: dict):
    account_id = payload.get("account_id")
    if not account_id:
        return
    new_ids = await mail.sync_account(account_id, payload.get("limit", 50))
    for mid in new_ids:
        await jobs.enqueue("mail_categorize", {"message_id": mid})


@jobs.register("mail_categorize")
async def mail_categorize(payload: dict):
    import json
    msg = await mail.get_message(payload.get("message_id", ""))
    if not msg:
        return
    content = f"From: {msg['from_addr']}\nSubject: {msg['subject']}\n\n{msg['snippet']}"
    try:
        raw = await llm.cheap(
            [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": content}],
            temperature=0.0, max_tokens=80,
        )
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        parsed = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        category = parsed.get("category", "other")
        if category not in CATEGORIES:
            category = "other"
        await mail.set_category(msg["id"], category, parsed.get("reason", ""))
    except Exception:
        await mail.set_category(msg["id"], "other", "auto-categorize failed")


async def draft_reply(message_id: str) -> dict | None:
    """On-demand draft (big model). Returns a saved, unsent draft."""
    msg = await mail.get_message(message_id)
    if not msg:
        return None
    system = ("Draft a concise, professional reply to this email. "
              "Output only the reply body, no subject line, no salutation placeholders.")
    content = f"From: {msg['from_addr']}\nSubject: {msg['subject']}\n\n{msg['snippet']}"
    body = await llm.complete(
        [{"role": "system", "content": system}, {"role": "user", "content": content}],
        temperature=0.4,
    )
    return await mail.save_draft(message_id, body)


def register_schedule(poll_seconds: int = 300):
    async def poll():
        for acc in await mail.list_accounts():
            await jobs.enqueue("mail_sync", {"account_id": acc["id"]})
    jobs.add_periodic(poll, seconds=poll_seconds, job_id="mail_poll")
