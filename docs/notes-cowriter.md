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

## Ingest on save — removed

Notes no longer write into the memory atom store. The `ingest_note` enqueue was removed from `routers/notes.py` in the Prescient Memory Part 1 update. The `ingest_note` job (`workers/cowriter.py`) still exists for backwards compatibility but is no longer triggered on save.

The reason: notes are personal writing — drafts, scratch thoughts, reference material — and having them show up verbatim as memory fragments created noise in chat context. Memory is for facts extracted from *conversation*, not for documents. Notes remain fully searchable through their own document index (FTS5 on the note body); they just don't become memory atoms.

The `workers/cowriter.py` guard remains: `memory_diff` notes (the weekly digest) are still explicitly blocked from ingestion should the job ever be re-enabled for other source kinds.

---

## What I didn't build (v1)

- **An authorship ledger** — tracking which spans of a note were written by me vs. the model. Recorded for v2; it needs a span-tracking data model the editor doesn't have yet.
- **Inline ghost-text suggestions** as I type. The actions are explicit (select → act) in v1, which is calmer and cheaper than continuous completion.
- **Diff/accept-reject UI** for rewrite and tighten. v1 streams the replacement; wiring a proper accept/reject is a frontend follow-up.
