"""Deep research pipeline (Part 2.3), as a background job.

planner (cheap) -> <=5 sub-questions
  -> sub-agents search IN PARALLEL (asyncio.gather)
  -> web_fetch top results -> chunk + embed into research_chunk(+_vec)
  -> synthesizer (big model) writes a grounded report with a plain source list
  -> persist report + sources
  -> push key findings to the shared memory substrate

No claim cards / contradiction detection in v1 (Part 6). Fan-out is parallel so
total time ~= slowest sub-agent + synthesis, not the sum.
"""
from __future__ import annotations

import asyncio
import json
import uuid

import numpy as np

from services import db, embeddings, llm, memory, search
from services import research as research_repo
from . import jobs

MAX_SUBQUESTIONS = 5
RESULTS_PER_SUBQ = 4
CHUNKS_PER_PAGE = 3
CHUNK_CHARS = 1000
SYNTH_CHUNKS = 16


def _strip_fences(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return raw


async def _plan(query: str) -> list[str]:
    try:
        raw = await llm.cheap(
            [{"role": "system", "content":
              "Decompose the research topic into at most 5 focused sub-questions. "
              "Return ONLY a JSON array of strings."},
             {"role": "user", "content": query}],
            temperature=0.2, max_tokens=300,
        )
        raw = _strip_fences(raw)
        arr = json.loads(raw[raw.find("["): raw.rfind("]") + 1])
        subqs = [s.strip() for s in arr if isinstance(s, str) and s.strip()][:MAX_SUBQUESTIONS]
        if subqs:
            return subqs
    except Exception:
        pass
    return [query, f"{query} overview", f"{query} analysis"]


def _chunk_text(text: str) -> list[str]:
    return [text[i:i + CHUNK_CHARS] for i in range(0, len(text), CHUNK_CHARS)][:CHUNKS_PER_PAGE]


async def _sub_agent(research_id: str, subq: str) -> list[dict]:
    """Search one sub-question, fetch top pages, chunk, embed, persist."""
    res = await search.search(subq, limit=RESULTS_PER_SUBQ)
    out: list[dict] = []
    for r in res.get("results", []):
        url, title = r.get("url", ""), r.get("title", "")
        page = await search.fetch_page(url) if url else ""
        body = page or r.get("content", "")
        if not body:
            continue
        for piece in _chunk_text(body):
            vec = await embeddings.embed(piece)
            chunk_id = str(uuid.uuid4())

            def op(conn, cid=chunk_id, url=url, title=title, piece=piece, vec=vec):
                conn.execute(
                    "INSERT INTO research_chunk(id, research_id, url, title, text, fetched_at) "
                    "VALUES(?,?,?,?,?,?)",
                    (cid, research_id, url, title, piece, db.now()),
                )
                rid_ = conn.execute("SELECT rowid FROM research_chunk WHERE id=?", (cid,)).fetchone()[0]
                conn.execute(
                    "INSERT INTO research_chunk_vec(rowid, embedding) VALUES(?,?)",
                    (rid_, db.serialize_f32(vec)),
                )

            await db.write(op)
            out.append({"url": url, "title": title, "text": piece, "vec": vec})
    return out


def _top_chunks(chunks: list[dict], query_vec: list[float], n: int) -> list[dict]:
    if not chunks:
        return []
    q = np.asarray(query_vec, dtype=np.float32)
    scored = sorted(chunks, key=lambda c: float(np.dot(q, np.asarray(c["vec"], dtype=np.float32))),
                    reverse=True)
    return scored[:n]


async def _synthesize(query: str, chunks: list[dict]) -> dict:
    context = ""
    for i, c in enumerate(chunks, 1):
        context += f"\n[{i}] {c['title']} ({c['url']})\n{c['text']}\n"
    system = (
        "You are a research analyst. Using ONLY the provided sources, write a grounded report. "
        "Return ONLY a JSON object (no fences): "
        '{"title":"...","summary":"2-3 sentences",'
        '"sections":[{"title":"...","content":"3-5 paragraphs"}],'
        '"key_findings":["...","..."]}. Aim for 4-6 sections. Be specific and cite facts from the sources.'
    )
    raw = await llm.complete(
        [{"role": "system", "content": system},
         {"role": "user", "content": f"Topic: {query}\n\nSources:{context}"}],
        temperature=0.3,
    )
    raw = _strip_fences(raw)
    return json.loads(raw[raw.find("{"): raw.rfind("}") + 1])


@jobs.register("research")
async def run_research(payload: dict):
    research_id = payload["research_id"]
    entry = await research_repo.get(research_id)
    if not entry:
        return
    query = entry["query"]
    try:
        subqs = await _plan(query)
        # Fan out IN PARALLEL — this is the whole point of the budget note.
        gathered = await asyncio.gather(*[_sub_agent(research_id, sq) for sq in subqs])
        chunks = [c for sub in gathered for c in sub]

        query_vec = await embeddings.embed(query)
        top = _top_chunks(chunks, query_vec, SYNTH_CHUNKS)
        if not top:
            await research_repo.mark_error(research_id, "No web sources could be fetched.")
            return

        report = await _synthesize(query, top)

        # Distinct sources, preserving order.
        seen, sources = set(), []
        for c in top:
            if c["url"] and c["url"] not in seen:
                seen.add(c["url"])
                sources.append({"url": c["url"], "title": c["title"]})

        await research_repo.save_result(
            research_id,
            title=report.get("title", query),
            summary=report.get("summary", ""),
            sections=report.get("sections", []),
            sources=sources,
        )

        # Push key findings into the shared memory substrate.
        for finding in report.get("key_findings", []):
            if isinstance(finding, str) and finding.strip():
                await memory.add_atom(
                    text=finding.strip(), type_="fact",
                    source_kind="research", source_id=research_id, dedup=True,
                )
    except Exception as e:  # noqa: BLE001
        await research_repo.mark_error(research_id, str(e))
        raise
