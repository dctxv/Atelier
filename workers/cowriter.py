"""Note ingestion job (Part 2.4 integration).

Saved notes flow into the shared memory substrate. To avoid piling up
duplicates every autosave, ingestion is replace-then-insert per note: it drops
the note's existing atoms and re-adds a single trimmed atom. Embedding/ingest
happens on save/idle, never per keystroke (the router enqueues this job).
"""
from __future__ import annotations

from services import db, memory, notes
from . import jobs


@jobs.register("ingest_note")
async def ingest_note(payload: dict):
    note_id = payload.get("note_id")
    if not note_id:
        return
    note = await notes.get(note_id)
    if not note:
        return
    if note.get("source_kind") == "memory_diff":
        return  # never ingest digest notes — memory-about-memory recursion

    # Drop prior atoms for this note.
    old = await db.fetchall(
        "SELECT id FROM memory_atom WHERE source_kind='note' AND source_id=?", (note_id,)
    )
    for o in old:
        await memory.delete_atom(o["id"])

    body = (note.get("body") or "").strip()
    if not body:
        return
    title = (note.get("title") or "").strip()
    text = f"{title}: {body}" if title and title != "Untitled Note" else body
    await memory.add_atom(
        text=text[:1000], type_="note", source_kind="note", source_id=note_id, dedup=True
    )
