"""Research repository (DB-backed). The actual deep-research pipeline runs as a
background job in workers/research.py and writes results back through here.
"""
from __future__ import annotations

import uuid

from . import db


async def list_research() -> list[dict]:
    rows = await db.fetchall("SELECT * FROM research ORDER BY created_at DESC")
    return rows


async def get(research_id: str) -> dict | None:
    r = await db.fetchone("SELECT * FROM research WHERE id=?", (research_id,))
    if not r:
        return None
    sections = await db.fetchall(
        "SELECT title, content FROM research_section WHERE research_id=? ORDER BY idx", (research_id,)
    )
    sources = await db.fetchall(
        "SELECT url, title FROM research_source WHERE research_id=?", (research_id,)
    )
    r["sections"] = sections
    r["sources"] = sources
    return r


async def create(query: str) -> dict:
    rid = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO research(id, query, status, title, summary, created_at) VALUES(?,?,?,?,?,?)",
        (rid, query, "running", query, "", db.now()),
    )
    return await get(rid)


async def save_result(research_id: str, title: str, summary: str,
                      sections: list[dict], sources: list[dict]):
    def op(conn):
        conn.execute(
            "UPDATE research SET status='done', title=?, summary=?, completed_at=?, error=NULL WHERE id=?",
            (title, summary, db.now(), research_id),
        )
        conn.execute("DELETE FROM research_section WHERE research_id=?", (research_id,))
        conn.execute("DELETE FROM research_source WHERE research_id=?", (research_id,))
        for idx, sec in enumerate(sections):
            conn.execute(
                "INSERT INTO research_section(id, research_id, idx, title, content) VALUES(?,?,?,?,?)",
                (str(uuid.uuid4()), research_id, idx, sec.get("title", ""), sec.get("content", "")),
            )
        for src in sources:
            conn.execute(
                "INSERT INTO research_source(id, research_id, url, title) VALUES(?,?,?,?)",
                (str(uuid.uuid4()), research_id, src.get("url", ""), src.get("title", "")),
            )

    await db.write(op)


async def mark_error(research_id: str, error: str):
    await db.execute(
        "UPDATE research SET status='error', error=?, completed_at=? WHERE id=?",
        (error, db.now(), research_id),
    )


async def delete(research_id: str) -> bool:
    existing = await db.fetchone("SELECT id FROM research WHERE id=?", (research_id,))
    if not existing:
        return False

    def op(conn):
        conn.execute("DELETE FROM research WHERE id=?", (research_id,))
        conn.execute("DELETE FROM research_section WHERE research_id=?", (research_id,))
        conn.execute("DELETE FROM research_source WHERE research_id=?", (research_id,))

    await db.write(op)
    return True
