"""AI flashcard generation (Part 2.5) — cheap model, background-eligible."""
from __future__ import annotations

import json

from services import flashcards, llm
from . import jobs

_SYSTEM = (
    "You create study flashcards from the provided material. "
    "Return ONLY a JSON array (no fences) of objects: "
    '{"front":"<question/term>","back":"<answer/definition>"}. '
    "Make atomic, single-fact cards. Aim for the requested count."
)


def _parse(raw: str):
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    s, e = raw.find("["), raw.rfind("]")
    if s == -1 or e == -1:
        return []
    try:
        return json.loads(raw[s:e + 1])
    except Exception:
        return []


async def generate_cards(deck_id: str, source_text: str, count: int = 10,
                         source_kind: str | None = None, source_id: str | None = None) -> list[dict]:
    raw = await llm.cheap(
        [{"role": "system", "content": _SYSTEM},
         {"role": "user", "content": f"Make about {count} cards from:\n\n{source_text[:6000]}"}],
        temperature=0.3, max_tokens=1500,
    )
    created = []
    for item in _parse(raw):
        front, back = (item.get("front") or "").strip(), (item.get("back") or "").strip()
        if front and back:
            created.append(await flashcards.add_card(deck_id, front, back, source_kind, source_id))
    return created


@jobs.register("generate_cards")
async def generate_cards_job(payload: dict):
    await generate_cards(
        payload["deck_id"], payload.get("source_text", ""), payload.get("count", 10),
        payload.get("source_kind"), payload.get("source_id"),
    )
