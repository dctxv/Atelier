# Email triage

*The heaviest, highest-risk feature — built last, on purpose. Written by Clay.*

---

## What it does

Connect an IMAP account; the Atelier syncs recent messages into SQLite in the background, categorizes each one, and can draft replies on demand. The one rule I will not bend: **the server never sends email on its own.** Sending only ever happens when I explicitly click send.

```
mail_account(id, address, protocol, creds_enc, created_at)
mail_message(id, account_id, uid, from_addr, subject, snippet, received_at,
             category, category_reason)
mail_draft(id, in_reply_to, body, created_at, sent_at)
```

## The flow

- **Account setup** stores IMAP/SMTP credentials as an **encrypted** blob (`services/crypto`, same Fernet as endpoint keys). No plaintext, ever. Prefer OAuth for Gmail and an app-specific password for iCloud; v1 accepts an app password / token in the encrypted creds.
- **Sync** is a background job, polled every 5 minutes (and on demand). It connects over IMAP-SSL, pulls recent headers + a short body peek, and upserts by `uid` so re-syncing doesn't duplicate. IMAP and SMTP are blocking stdlib calls, so they run in `asyncio.to_thread` — they never block the event loop.
- **Categorize** is a per-message background job using the cheap model: one category from a fixed list (`important, personal, work, newsletter, promotion, social, spam, other`) plus a short `category_reason`. Failures fall back to `other` rather than erroring.
- **Draft** is on demand and is the *only* big-model use in email. It produces a reply body and saves it as an unsent `mail_draft`.
- **Send** is a separate, explicit endpoint action. It's the only thing that calls SMTP, it's never a background job, and it stamps `sent_at` when done.

Why last and why careful: email is the feature where a bug isn't a wrong pixel, it's an embarrassing message sent to a real person. So the architecture makes autonomous sending *impossible by construction* — there is no code path from sync or categorize to send.

> Note: this is the one phase I couldn't fully exercise live, because it needs a real mailbox. The structure, encryption, threading, and the explicit-send boundary are all in place and the endpoints respond; the IMAP/SMTP round-trip is what I'll smoke-test against my own account.

---

## What I didn't build (v1)

- **A commitments extractor** — pulling "I'll send this Friday" type promises out of mail into memory/tasks. v2.
- **Memory-grounded drafts** — drafts that cite what I actually know from memory. The hook (drafts use the big model) is there; the grounding is v2.
- **Threading / conversation view.** v1 is a flat message list per account.
- **OAuth flows in-app.** v1 takes an app password; a proper Gmail OAuth dance is a later addition.
