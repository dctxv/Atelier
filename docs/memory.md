# Memory — the hub

*How the Atelier remembers things, and why it's the center of everything. Written by Clay.*

---

## What memory is now

In the JSON era, "memory" was a list of text fragments I could add and view. Useful, but inert — nothing wrote to it automatically and nothing read from it. In v1, memory is **the hub**: the single place every surface writes durable facts to, and the single place every surface reads context from. Chat, research, and notes all feed it; chat, the co-writer, and drafts all draw from it. (See the integration model in [shared-core.md](shared-core.md).)

A unit of memory is an **atom**: a short piece of text plus a type, a salience, a source reference, timestamps, and a pinned flag. Each atom also has a vector (in `memory_vec`) and an FTS row (in `memory_fts`), all keyed by the atom's integer rowid.

```
memory_atom(id, text, type, salience, source_kind, source_id,
            created_at, last_used_at, pinned)
memory_vec   -- sqlite-vec vec0, float[256], cosine
memory_fts   -- FTS5 keyword index
```

`services/memory.py` writes all three inside **one serialized transaction**. That matters: there is never a vector without its atom, or an FTS row pointing at a deleted atom. Delete is symmetric — it removes the row from all three tables.

---

## How atoms get created (extraction)

After a chat turn finishes streaming, the chat router enqueues an `extract_memory` job (it does *not* extract inline — hot-path rule 1). The job (`workers/extraction.py`) runs the **cheap** model over the turn and asks for durable, reusable facts about me as a strict JSON array: `{text, type, salience}`. Only things worth keeping across sessions — preferences, identity, goals, ongoing projects, key facts. If there's nothing worth keeping, it returns `[]`.

Each extracted fact is written with `source_kind="chat"` and the session id as `source_id`, so the atom always knows where it came from. Research findings come in the same way with `source_kind="research"`; saved notes with `source_kind="note"`.

If no model is configured, extraction simply doesn't happen that turn. It never errors into the user's face, because it's never on the user's path.

---

## Dedup

When `add_atom(..., dedup=True)` runs, it first does a nearest-neighbour vector search. If the closest existing atom is ≥ **0.92** cosine similarity, it treats the new fact as a restatement: instead of inserting a duplicate, it bumps the existing atom's salience and refreshes its `last_used_at`. Below the threshold, it inserts. Manual additions through the UI skip dedup (if I typed it, I meant it); extraction and ingestion use it.

0.92 is deliberately high. I'd rather keep two slightly-different facts than silently merge two things that only looked similar.

---

## Consolidation

A periodic job (every 6 hours) is the janitor. In v1 it does three modest things:

1. **Drops exact-duplicate texts**, keeping the oldest / most-pinned copy.
2. **Drops orphans** — atoms whose chat `source_id` no longer points at an existing session. This is what makes "deleting a source turn removes its atom on next consolidation" true.
3. **Caps growth** — beyond a safety ceiling (50k), it trims the oldest, lowest-salience, unpinned atoms.

That's it. No self-correction, no version chains, no decay. Those are real ideas and they're recorded in [v2-deferred.md](v2-deferred.md), but they layer *on top of* this baseline; they don't change it.

---

## Retrieval & chat injection

When I send a message, the chat router calls `retrieve()` with the last user message and a 700-token budget, formats the hits into a compact `[MEMORY]` block, and prepends it to the system prompt — reusing the *exact* mechanism that already injects skills. Then it streams the reply. Retrieval is a fast local read (~49ms p95 even at 50k atoms), so it doesn't delay the first token past budget.

The payoff is the thing I actually wanted: a fact I mention in one session shows up, used naturally, in a later session — without me repeating myself. That's the acceptance test for this whole phase, and it works.

The memory surface still lists atoms with their source and relative time, and the legacy API shape (`category`, `timestamp`) is preserved so the existing frontend didn't need rewriting — the router maps atom fields back to those names.

---

## What I didn't build (v1)

- **Self-correcting memory** — superseding a fact when a contradicting one arrives, with a version chain. Deferred (v2).
- **Memory "time-travel"** — "what did I believe as of last month" queries. Deferred (v2).
- **Salience decay (FSRS-style)** for memory — letting unused facts fade. Deferred (v2).
- **An entity/relation graph** over atoms. Deferred (v2).
- **Manual edit re-embedding nuance** — editing an atom's text *does* re-embed and rebuild its FTS row; that part's done. What's not done is surfacing *why* an atom was retrieved (provenance), which belongs with the v2 provenance layer.
