# Deferred to v2

*Everything I deliberately did not build in v1, recorded so it isn't lost. Written by Clay.*

---

## The principle

v1's goal was every feature working in its simplest correct form, all of them communicating through one shared core, with the latency proven. The explicit non-goal was cleverness. The ideas below are good — some of them are the *reason* I built the core the way I did — but each one layers on top of the working baseline without re-architecting it. So they wait until v1 is verified, which it now is.

I'm recording them here, with the v1 hooks that already exist for them, so future-me doesn't rediscover the same designs from scratch.

---

## The Provenance Layer / Analyst Mode

Break a research report (and eventually any answer) into individual **claims**, each with its evidence, a local entailment check, a confidence split, and contradiction detection across sources. Tables would be `claim`, `claim_evidence`. This is the largest deferred item and the most interesting.

*v1 hook:* research already stores chunks and sources; the synthesizer already produces discrete findings. Claims are a refinement of that, not a new pipeline.

## Self-correcting memory

When a new fact contradicts an existing one, supersede it with a version chain rather than keeping both. Plus **memory time-travel** ("what did I believe as of date X").

*v1 hook:* atoms have `source_id`, `created_at`, and consolidation already runs; superseding is a new consolidation rule plus a version pointer.

## Memory decay

FSRS-style salience decay so unused facts fade and the truly-used ones stay sharp. (Note the irony: I'm already running FSRS for flashcards, so the math is in the building.)

*v1 hook:* atoms have `salience` and `last_used_at` — currently used only mildly. Decay reads those.

## Entity / relation graph

An `entity` + `relation` model over atoms, and a graph view of how people/projects/facts connect.

## Notes authorship ledger

Track which spans of a note are mine vs. the model's (`note_span`). Needs span tracking the editor doesn't have yet.

## Self-invalidating flashcards

A card flags itself stale when its source note/report changes, and conversational active recall (being quizzed in chat).

*v1 hook:* every card already stores a `source_id` link precisely so this is cheap to add.

## Zero-knowledge / burn-after-read shares

Client-side encryption so the server never sees plaintext, and one-read self-destructing links.

*v1 hook:* shares already enforce expiry + download count through the validating handler; these are stronger variants of the same gate.

## Email commitments extractor + grounded drafts

Pull promises ("I'll send Friday") out of mail into memory/tasks, and make drafts cite what I actually know.

*v1 hook:* mail facts can already flow to memory; drafts already use the big model.

---

## Tables intentionally NOT created in v1

`claim`, `claim_evidence`, `entity`, `relation`, `note_span`. They're v2. The v1 schema is in `services/schema.sql` and stops exactly at the baseline.
