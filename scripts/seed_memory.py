"""Seed N synthetic memory atoms for the Part 4 scaling test.

Usage:  python -m scripts.seed_memory 50000
Inserts in batches through the single writer. Uses the local hashing embedding
(fast, offline) so the scaling test measures retrieval, not embedding cost.
"""
from __future__ import annotations

import asyncio
import random
import sys
import uuid

from services import db, embeddings

SUBJECTS = ["Clay", "the project", "the model", "the database", "the user", "the team",
            "research", "the note", "the deck", "the endpoint", "memory", "the server"]
VERBS = ["prefers", "uses", "avoids", "documented", "configured", "tested", "shipped",
         "measured", "cached", "indexed", "scheduled", "deferred"]
OBJECTS = ["dark mode", "SQLite WAL", "sqlite-vec", "FSRS scheduling", "the cheap model",
           "parallel fan-out", "the single writer", "int8 vectors", "RRF fusion",
           "the share token", "the IMAP sync", "Matryoshka truncation", "PowerShell",
           "the hot path", "background jobs", "the token budget"]


def _sentence(i: int) -> str:
    return (f"{random.choice(SUBJECTS)} {random.choice(VERBS)} {random.choice(OBJECTS)} "
            f"in context #{i} ({random.choice(OBJECTS)}).")


async def main(n: int, batch: int = 1000):
    await db.init_db()
    start_count = await db.fetchone("SELECT COUNT(*) AS n FROM memory_atom")
    print(f"starting atoms: {start_count['n']}; seeding {n}...")

    inserted = 0
    while inserted < n:
        rows = []
        size = min(batch, n - inserted)
        for i in range(size):
            text = _sentence(inserted + i)
            vec = await embeddings.embed(text)
            rows.append((str(uuid.uuid4()), text, db.serialize_f32(vec)))

        def op(conn, rows=rows):
            for atom_id, text, payload in rows:
                ts = db.now()
                conn.execute(
                    "INSERT INTO memory_atom(id, text, type, salience, source_kind, created_at, "
                    "last_used_at, pinned) VALUES(?,?,?,?,?,?,?,?)",
                    (atom_id, text, "fact", 1.0, "seed", ts, ts, 0),
                )
                rid = conn.execute("SELECT rowid FROM memory_atom WHERE id=?", (atom_id,)).fetchone()[0]
                conn.execute("INSERT INTO memory_vec(rowid, embedding) VALUES(?,?)", (rid, payload))
                conn.execute("INSERT INTO memory_fts(rowid, text) VALUES(?,?)", (rid, text))

        await db.write(op)
        inserted += size
        print(f"  {inserted}/{n}")

    total = await db.fetchone("SELECT COUNT(*) AS n FROM memory_atom")
    print(f"done. total atoms: {total['n']}")


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 50_000
    asyncio.run(main(count))
