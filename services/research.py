"""Research repository (DB-backed). The actual deep-research pipeline runs as a
background job in workers/research.py and writes results back through here.
"""
from __future__ import annotations

import json
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
        "SELECT url, title FROM research_source WHERE research_id=? ORDER BY rowid", (research_id,)
    )
    meta_row = await db.fetchone(
        "SELECT meta FROM research_meta WHERE research_id=?", (research_id,)
    )
    r["sections"] = sections
    r["sources"] = sources
    r["claims"] = await _load_claims(research_id, sources)
    # Contradictions = claims the verifier flagged as disputed (sources disagree).
    r["contradictions"] = [
        {"text": c["text"], "citations": c["citations"]}
        for c in r["claims"] if c.get("stance") == "disputed"
    ]
    if meta_row and meta_row.get("meta"):
        try:
            r["stats"] = json.loads(meta_row["meta"])
        except Exception:
            pass
    return r


async def _load_claims(research_id: str, sources: list[dict]) -> list[dict]:
    """Claims grouped with their evidence, each citation mapped to a 1-based
    source index so the frontend can render inline [n] markers."""
    rows = await db.fetchall(
        "SELECT id, text, section_idx, confidence, stance FROM claim "
        "WHERE research_id=? ORDER BY section_idx, rowid", (research_id,)
    )
    if not rows:
        return []
    url_to_idx = {s["url"]: i + 1 for i, s in enumerate(sources) if s.get("url")}
    out: list[dict] = []
    for c in rows:
        ev = await db.fetchall(
            "SELECT url, polarity, published_at FROM claim_evidence WHERE claim_id=?", (c["id"],)
        )
        cites: list[dict] = []
        seen: set[str] = set()
        for e in ev:
            u = e.get("url")
            if not u or u in seen:
                continue
            seen.add(u)
            cites.append({"url": u, "source_idx": url_to_idx.get(u),
                          "polarity": e.get("polarity")})
        out.append({**c, "citations": cites})
    return out


async def create(query: str) -> dict:
    rid = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO research(id, query, status, title, summary, created_at) VALUES(?,?,?,?,?,?)",
        (rid, query, "running", query, "", db.now()),
    )
    return await get(rid)


async def reset_progress(research_id: str):
    """Clear any prior partial output so a (re)run is idempotent."""
    def op(conn):
        conn.execute(
            "DELETE FROM claim_evidence WHERE claim_id IN "
            "(SELECT id FROM claim WHERE research_id=?)", (research_id,))
        for t in ("research_section", "research_source", "claim", "entity", "relation"):
            conn.execute(f"DELETE FROM {t} WHERE research_id=?", (research_id,))

    await db.write(op)


async def save_sources(research_id: str, sources: list[dict]):
    """Persist the cited-source list (ranked order). Called before synthesis so
    the Sources panel populates while the report is still being written."""
    def op(conn):
        conn.execute("DELETE FROM research_source WHERE research_id=?", (research_id,))
        for src in sources:
            conn.execute(
                "INSERT INTO research_source(id, research_id, url, title) VALUES(?,?,?,?)",
                (str(uuid.uuid4()), research_id, src.get("url", ""), src.get("title", "")),
            )

    await db.write(op)


async def upsert_section(research_id: str, idx: int, title: str, content: str):
    """Insert/replace one section as soon as it's synthesized (live rendering)."""
    def op(conn):
        conn.execute("DELETE FROM research_section WHERE research_id=? AND idx=?",
                     (research_id, idx))
        conn.execute(
            "INSERT INTO research_section(id, research_id, idx, title, content) VALUES(?,?,?,?,?)",
            (str(uuid.uuid4()), research_id, idx, title, content),
        )

    await db.write(op)


async def add_claim(research_id: str, text: str, section_idx: int,
                    confidence: float, stance: str, evidence: list[dict]) -> str:
    """Persist one verified claim and its evidence immediately."""
    cid = str(uuid.uuid4())
    ts = db.now()

    def op(conn):
        conn.execute(
            "INSERT INTO claim(id, research_id, text, section_idx, confidence, stance, created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (cid, research_id, text, section_idx, confidence, stance, ts),
        )
        for ev in evidence:
            conn.execute(
                "INSERT INTO claim_evidence(id, claim_id, chunk_id, url, published_at,"
                " entail, polarity, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), cid, ev.get("chunk_id"), ev.get("url"),
                 ev.get("published_at"), ev.get("entail", 0.0),
                 ev.get("polarity", "neutral"), ts),
            )

    await db.write(op)
    return cid


async def save_result(research_id: str, title: str, summary: str,
                      sections: list[dict], sources: list[dict],
                      stats: dict | None = None):
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
        if stats:
            conn.execute(
                "INSERT OR REPLACE INTO research_meta(research_id, meta) VALUES(?,?)",
                (research_id, json.dumps(stats)),
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
        conn.execute("DELETE FROM claim WHERE research_id=?", (research_id,))
        conn.execute("DELETE FROM entity WHERE research_id=?", (research_id,))
        conn.execute("DELETE FROM relation WHERE research_id=?", (research_id,))
        conn.execute("DELETE FROM research_meta WHERE research_id=?", (research_id,))

    await db.write(op)
    return True
