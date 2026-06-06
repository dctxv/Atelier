"""Flashcards with FSRS-6 scheduling (Part 2.5).

Scheduling uses the maintained `fsrs` library (FSRS-6) — we do NOT reimplement
the algorithm. The library's Card is the source of truth, stored as JSON on the
row; we also mirror a few fields (due_at, stability, difficulty, reps, lapses,
state) into columns for cheap querying and display.

Review is pure local compute — zero tokens, instant (hot-path: review loop is
local-only). AI card generation uses the cheap model and is background-eligible.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fsrs import Card, Rating, Scheduler

from . import db

_scheduler = Scheduler()

_RATING_MAP = {1: Rating.Again, 2: Rating.Hard, 3: Rating.Good, 4: Rating.Easy}


def _epoch(dt: datetime | None) -> int | None:
    return int(dt.timestamp()) if dt else None


def _persist_fields(card: Card) -> dict:
    return {
        "fsrs_json": card.to_json(),
        "due_at": _epoch(card.due),
        "stability": card.stability,
        "difficulty": card.difficulty,
        "state": int(card.state),
        "step": card.step,
        "last_review_at": _epoch(card.last_review),
    }


# ── Decks ─────────────────────────────────────────────────────────────────────

async def list_decks() -> list[dict]:
    rows = await db.fetchall(
        "SELECT d.*, "
        "(SELECT COUNT(*) FROM card c WHERE c.deck_id=d.id) AS card_count, "
        "(SELECT COUNT(*) FROM card c WHERE c.deck_id=d.id AND c.due_at<=?) AS due_count "
        "FROM deck d ORDER BY d.created_at DESC",
        (db.now(),),
    )
    return rows


async def create_deck(name: str) -> dict:
    did = str(uuid.uuid4())
    await db.execute("INSERT INTO deck(id, name, created_at) VALUES(?,?,?)", (did, name.strip() or "Deck", db.now()))
    return {"id": did, "name": name, "card_count": 0, "due_count": 0, "created_at": db.now()}


async def delete_deck(deck_id: str) -> bool:
    existing = await db.fetchone("SELECT id FROM deck WHERE id=?", (deck_id,))
    if not existing:
        return False

    def op(conn):
        conn.execute("DELETE FROM review_log WHERE card_id IN (SELECT id FROM card WHERE deck_id=?)", (deck_id,))
        conn.execute("DELETE FROM card WHERE deck_id=?", (deck_id,))
        conn.execute("DELETE FROM deck WHERE id=?", (deck_id,))

    await db.write(op)
    return True


# ── Cards ─────────────────────────────────────────────────────────────────────

async def add_card(deck_id: str, front: str, back: str,
                   source_kind: str | None = None, source_id: str | None = None) -> dict:
    cid = str(uuid.uuid4())
    card = Card()
    fields = _persist_fields(card)
    await db.execute(
        "INSERT INTO card(id, deck_id, front, back, source_kind, source_id, stability, difficulty, "
        "due_at, reps, lapses, last_review_at, state, step, fsrs_json, created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (cid, deck_id, front.strip(), back.strip(), source_kind, source_id,
         fields["stability"], fields["difficulty"], fields["due_at"], 0, 0,
         fields["last_review_at"], fields["state"], fields["step"], fields["fsrs_json"], db.now()),
    )
    return await get_card(cid)


async def import_lines(deck_id: str, text: str, sep: str = ",") -> int:
    """Paste import: one `term<sep>definition` per line."""
    n = 0
    for line in text.splitlines():
        line = line.strip()
        if not line or sep not in line:
            continue
        front, back = line.split(sep, 1)
        if front.strip() and back.strip():
            await add_card(deck_id, front, back)
            n += 1
    return n


async def get_card(card_id: str) -> dict | None:
    r = await db.fetchone("SELECT * FROM card WHERE id=?", (card_id,))
    return r


async def list_cards(deck_id: str) -> list[dict]:
    return await db.fetchall("SELECT * FROM card WHERE deck_id=? ORDER BY created_at", (deck_id,))


async def due_cards(deck_id: str, limit: int = 50) -> list[dict]:
    return await db.fetchall(
        "SELECT * FROM card WHERE deck_id=? AND due_at<=? ORDER BY due_at LIMIT ?",
        (deck_id, db.now(), limit),
    )


async def review(card_id: str, rating: int) -> dict | None:
    row = await db.fetchone("SELECT * FROM card WHERE id=?", (card_id,))
    if not row:
        return None
    rating_enum = _RATING_MAP.get(int(rating), Rating.Good)

    card = Card.from_json(row["fsrs_json"]) if row.get("fsrs_json") else Card()
    prev_last = card.last_review
    now = datetime.now(timezone.utc)
    new_card, _log = _scheduler.review_card(card, rating_enum, review_datetime=now)

    fields = _persist_fields(new_card)
    elapsed_days = ((now - prev_last).total_seconds() / 86400) if prev_last else 0.0
    scheduled_days = (new_card.due - now).total_seconds() / 86400
    lapses = row["lapses"] + (1 if rating_enum == Rating.Again else 0)

    def op(conn):
        conn.execute(
            "UPDATE card SET stability=?, difficulty=?, due_at=?, reps=reps+1, lapses=?, "
            "last_review_at=?, state=?, step=?, fsrs_json=? WHERE id=?",
            (fields["stability"], fields["difficulty"], fields["due_at"], lapses,
             fields["last_review_at"], fields["state"], fields["step"], fields["fsrs_json"], card_id),
        )
        conn.execute(
            "INSERT INTO review_log(id, card_id, rating, reviewed_at, elapsed_days, scheduled_days) "
            "VALUES(?,?,?,?,?,?)",
            (str(uuid.uuid4()), card_id, int(rating), db.now(), elapsed_days, scheduled_days),
        )

    await db.write(op)
    return await get_card(card_id)


async def delete_card(card_id: str) -> bool:
    existing = await db.fetchone("SELECT id FROM card WHERE id=?", (card_id,))
    if not existing:
        return False

    def op(conn):
        conn.execute("DELETE FROM review_log WHERE card_id=?", (card_id,))
        conn.execute("DELETE FROM card WHERE id=?", (card_id,))

    await db.write(op)
    return True
