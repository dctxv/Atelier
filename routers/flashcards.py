"""Flashcards: decks, cards, paste import, review loop, AI generation."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from services import flashcards
from services import notes as notes_svc
from services import research as research_repo
from workers import cards as cards_worker

router = APIRouter(prefix="/api")


@router.get("/decks")
async def list_decks():
    return {"decks": await flashcards.list_decks()}


@router.post("/decks")
async def create_deck(request: Request):
    data = await request.json()
    if not (data.get("name") or "").strip():
        raise HTTPException(400, "Deck name required")
    return {"ok": True, "deck": await flashcards.create_deck(data["name"])}


@router.delete("/decks/{deck_id}")
async def delete_deck(deck_id: str):
    if not await flashcards.delete_deck(deck_id):
        raise HTTPException(404, "Deck not found")
    return {"ok": True}


@router.get("/decks/{deck_id}/cards")
async def list_cards(deck_id: str):
    return {"cards": await flashcards.list_cards(deck_id)}


@router.get("/decks/{deck_id}/due")
async def due_cards(deck_id: str):
    return {"cards": await flashcards.due_cards(deck_id)}


@router.post("/decks/{deck_id}/cards")
async def add_card(deck_id: str, request: Request):
    data = await request.json()
    if not (data.get("front") and data.get("back")):
        raise HTTPException(400, "front and back required")
    return {"ok": True, "card": await flashcards.add_card(deck_id, data["front"], data["back"])}


@router.post("/decks/{deck_id}/import")
async def import_cards(deck_id: str, request: Request):
    data = await request.json()
    n = await flashcards.import_lines(deck_id, data.get("text", ""), data.get("sep", ","))
    return {"ok": True, "imported": n}


@router.post("/cards/{card_id}/review")
async def review_card(card_id: str, request: Request):
    data = await request.json()
    card = await flashcards.review(card_id, int(data.get("rating", 3)))
    if not card:
        raise HTTPException(404, "Card not found")
    return {"ok": True, "card": card}


@router.delete("/cards/{card_id}")
async def delete_card(card_id: str):
    if not await flashcards.delete_card(card_id):
        raise HTTPException(404, "Card not found")
    return {"ok": True}


@router.post("/decks/{deck_id}/generate")
async def generate_cards(deck_id: str, request: Request):
    """Make cards from raw text, a note, or a research report (cheap model)."""
    data = await request.json()
    text = data.get("source_text", "")
    if data.get("note_id"):
        note = await notes_svc.get(data["note_id"])
        text = f"{note['title']}\n{note['body']}" if note else text
    elif data.get("research_id"):
        item = await research_repo.get(data["research_id"])
        if item:
            text = item.get("summary", "") + "\n\n" + "\n\n".join(
                s.get("content", "") for s in item.get("sections", [])
            )
    if not text.strip():
        raise HTTPException(400, "No source content to generate from")
    created = await cards_worker.generate_cards(
        deck_id, text, int(data.get("count", 10)),
        source_kind="note" if data.get("note_id") else ("research" if data.get("research_id") else None),
        source_id=data.get("note_id") or data.get("research_id"),
    )
    return {"ok": True, "created": created, "count": len(created)}
