# Flashcards

*Spaced repetition that I didn't write the algorithm for. Written by Clay.*

---

## What it does

Decks of cards, reviewed on a spaced-repetition schedule. Three ways to make cards:

1. **Paste import** — one `term, definition` per line. Split on the first comma, trim, skip blank or malformed lines. A pasted block becomes a scheduled deck in one request.
2. **Manual** — add a single front/back.
3. **AI generation** — "make cards from this note / this research report." The cheap model reads the source and returns atomic front/back pairs. Each generated card stores a `source_id` link back to where it came from.

Review is pure local compute: load due cards, show front, rate Again/Hard/Good/Easy, reschedule. Zero tokens, instant.

---

## FSRS — using the library, not reinventing it

The scheduling is **FSRS-6** via the maintained `fsrs` library (v6.3.1). I did not reimplement the algorithm, and I won't — getting spaced repetition subtly wrong is worse than not having it. The library's `Card` object is the source of truth; I store its full JSON round-trip in the `fsrs_json` column and *also* mirror a few fields (`due_at`, `stability`, `difficulty`, `reps`, `lapses`, `state`, `step`) into columns so I can cheaply query "what's due" and show stats without deserializing every card.

The review flow:
```
load card → Card.from_json → scheduler.review_card(card, rating, now)
          → persist new fields + append a review_log row
```
`due_cards(deck_id)` is just `WHERE due_at <= now ORDER BY due_at`. The deck list carries a live `due_count` so I can see at a glance what needs attention.

I verified it end to end: imported three capitals, reviewed one "Good," and watched stability jump to 2.3 and the due date move out ten minutes (it was in the learning step), with a `review_log` row written.

---

## What I didn't build (v1)

- **Self-invalidating cards** — a card going stale when its `source_id` (a note/report) changes. The `source_id` link is stored precisely so this is cheap to add later, but the stale-detection itself is v2.
- **Conversational active recall** — being quizzed in chat instead of a review screen. v2.
- **Custom FSRS parameter optimization** from my own review history. The library supports it; I'm using defaults until I have enough reviews for it to matter.
- **Cloze deletions / image cards / rich formatting.** Front and back are plain text in v1.
