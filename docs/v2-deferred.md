# Deferred

*Everything deliberately not yet built, recorded so it isn't lost. Written by Clay.*

---

## The principle

The goal of each phase has been every feature working in its simplest correct form, all communicating through one shared core. The ideas below are good — some of them are the *reason* I built the core the way I did — but each layers on top of the working baseline without re-architecting it. So they wait.

I'm recording them here, with the hooks that already exist for them, so future-me doesn't rediscover the same designs from scratch.

---

## ~~Self-correcting memory~~ ✓ shipped in v2

Supersession chains, retraction, read-time decay, the uncertainty register, and the full reconciliation engine all shipped as part of the Living Memory System v2. See [memory.md](memory.md).

## ~~Memory decay~~ ✓ shipped in v2

Read-time confidence decay with per-category grace periods and half-lives. Corroboration as the write-side counterpart. See [memory.md](memory.md).

---

## The Provenance Layer / Analyst Mode

Break a research report (and eventually any answer) into individual **claims**, each with its evidence, a local entailment check, a confidence split, and contradiction detection across sources. Tables would be `claim`, `claim_evidence`. This is the largest remaining deferred item and the most interesting.

*Hook:* research already stores chunks and sources; the synthesizer already produces discrete findings. Claims are a refinement of that, not a new pipeline.

## Entity / relation graph

An `entity` + `relation` model over atoms, and a graph view of how people/projects/facts connect. The v2 subject/predicate/object structure already produces the raw triples; the tables and the surface don't exist yet.

## Memory time-travel query surface

The timeline endpoint exists (`GET /api/memory/timeline?subject=&predicate=`) and walks the supersession chain for a given predicate. A general "what did I believe as of date X" query surface — not predicate-scoped — doesn't exist yet.

## Inline clarification during chat

`get_eligible_clarification()` in `services/questions.py` can identify a conflict worth asking about mid-session, but the chat router doesn't yet surface it inline. Questions go to the Review tab instead. The wiring is the missing piece.

## Notes authorship ledger

Track which spans of a note are mine vs. the model's (`note_span`). Needs span tracking the editor doesn't have yet.

## Self-invalidating flashcards

A card flags itself stale when its source note/report changes, and conversational active recall (being quizzed in chat).

*Hook:* every card already stores a `source_id` link precisely so this is cheap to add.

## Zero-knowledge / burn-after-read shares

Client-side encryption so the server never sees plaintext, and one-read self-destructing links.

*Hook:* shares already enforce expiry + download count through the validating handler; these are stronger variants of the same gate.

## Email commitments extractor + grounded drafts

Pull promises ("I'll send Friday") out of mail into memory/tasks, and make drafts cite what I actually know. The commitment routing from assistant turns already ships in v2; this is the inbound mail side.

*Hook:* mail facts can already flow to memory; drafts already use the big model.

---

## Tables intentionally not yet created

`claim`, `claim_evidence`, `entity`, `relation`, `note_span`. The v2 schema is in `services/schema.sql`.
