# Notes co-writer

*AI writing actions on top of the existing notes editor. Written by Clay.*

---

## What it does

The notes surface already had CRUD and autosave (see [surfaces.md](surfaces.md)). The co-writer adds three streamed AI actions over a selection or the current text:

- **continue** — keep writing from where I stopped, matching voice.
- **rewrite** — make the selected text clearer, same meaning.
- **tighten** — cut redundancy, keep the voice.

They stream token-by-token like chat, over SSE, from `/api/notes/cowrite`. Each action pulls context from the shared `retrieve()` (a 400-token slice) so the co-writer knows what the rest of my workspace knows before it writes a word.

The latency target is first-token < 300ms with a local model. That's a property of the model, not the app — the app overhead before the stream is just one fast retrieval call.

## Ingest on save, never per keystroke

When I save a note with content, the router enqueues an `ingest_note` job. That job (`workers/cowriter.py`) makes the note retrievable by writing it into memory (`source_kind="note"`). To avoid piling up a new atom on every autosave, ingestion is **replace-then-insert**: it deletes the note's prior atoms and writes one fresh, trimmed atom. Embedding happens in the background on save/idle — never on a keystroke (hot-path rule 1).

So: save a note, and its content becomes something chat and research can find. That's the acceptance test, and it's the same ingestion pipeline everything else uses.

---

## What I didn't build (v1)

- **An authorship ledger** — tracking which spans of a note were written by me vs. the model. Recorded for v2; it needs a span-tracking data model the editor doesn't have yet.
- **Inline ghost-text suggestions** as I type. The actions are explicit (select → act) in v1, which is calmer and cheaper than continuous completion.
- **Diff/accept-reject UI** for rewrite and tighten. v1 streams the replacement; wiring a proper accept/reject is a frontend follow-up.
