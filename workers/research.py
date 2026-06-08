"""Deep Research v2 — iterative claim loop (background job).

Pipeline
--------
[0] CONTEXT    retrieve() personal memory atoms (Phase 1)
[1] PLAN       cheap model → ≤MAX_SUBQUESTIONS sub-questions
loop (up to MAX_ROUNDS):
  [2] SEARCH   parallel search() per open sub-question (Phase 2 — recency-weighted)
  [3] INGEST   chunk + embed → research_chunk / research_chunk_vec
  [4] GAP      cheap model → coverage float + new sub-questions
  stop when coverage ≥ COVERAGE_TARGET, no new questions, or MAX_ROUNDS hit
[5] RANK       cosine top-k evidence pool
[6] SYNTH      big model → claims with chunk citations (Phase 3)
[7] VERIFY     cosine pre-filter → cheap NLI → confidence + stance (Phase 3)
[8] LINK       cheap model → entity/relation graph (Phase 5)
[9] PERSIST    report + claims + evidence + entities + relations
               push high-confidence claims → shared memory hub (dedup)

Progress events are pushed to an in-memory _ProgressStore keyed by research_id.
The SSE endpoint in routers/research.py streams them to the browser (Phase 4).
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from urllib.parse import urlparse

import numpy as np

from services import db, embeddings, llm, memory, retrieval, search
from services import research as research_repo
from . import jobs

# ── Knobs ──────────────────────────────────────────────────────────────────────
MAX_SUBQUESTIONS  = 5
MIN_ROUNDS        = 2        # always deepen at least once (when questions remain)
MAX_ROUNDS        = 3
COVERAGE_TARGET   = 0.85
MAX_TOTAL_SUBQ    = 15       # hard cap across all rounds
RESULTS_PER_SUBQ  = 6        # pages fetched per sub-question (bigger evidence pool)
CHUNKS_PER_PAGE   = 3
CHUNK_CHARS       = 1000
SYNTH_CHUNKS      = 24       # chunks handed to synthesis + corroboration
NLI_CONTEXT_CHARS = 900     # how much of each source passage the checker reads
EVIDENCE_MIN_COS  = 0.30    # below this a citation is kept but marked "set_aside"
CORROB_MIN_COS    = 0.42    # min similarity to try an uncited chunk as corroboration
CORROB_MAX_CHECKS = 4       # cap extra NLI calls per claim during corroboration
POOL_PER_DOMAIN   = 3       # cap chunks per domain in the evidence pool (diversity)
MEMORY_BUDGET     = 400     # token budget for personal context injection


# ── In-memory progress store (Phase 4) ────────────────────────────────────────

class _ProgressStore:
    """Append-only event log for one research job.

    The SSE endpoint replays events from index 0 so reconnects are safe.
    Uses asyncio.Event for instant notification; double-check after clear()
    eliminates the lost-wake race without busy-polling.
    """

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.done: bool = False
        self._signal: asyncio.Event = asyncio.Event()

    async def push(self, phase: str, **data: object) -> None:
        ev = {"phase": phase, **data}
        self.events.append(ev)
        if phase in ("done", "error"):
            self.done = True
        self._signal.set()

    async def stream(self, from_idx: int = 0):
        """Async generator — yields events, blocks efficiently between pushes."""
        idx = from_idx
        while True:
            while idx < len(self.events):
                yield self.events[idx]
                idx += 1
            if self.done:
                return
            self._signal.clear()
            if idx < len(self.events):
                continue  # new events arrived between the drain and clear()
            try:
                await asyncio.wait_for(self._signal.wait(), timeout=25.0)
            except asyncio.TimeoutError:
                yield {"phase": "heartbeat"}


_stores: dict[str, _ProgressStore] = {}


def get_store(research_id: str) -> _ProgressStore:
    if research_id not in _stores:
        _stores[research_id] = _ProgressStore()
    return _stores[research_id]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _strip_fences(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return raw


# ── Phase 0: Personal context ──────────────────────────────────────────────────

async def _get_context(query: str) -> str:
    atoms = await retrieval.retrieve(query, budget_tokens=MEMORY_BUDGET)
    return retrieval.format_block(atoms)


# ── Phase 1: Planning ──────────────────────────────────────────────────────────

async def _plan(query: str, context: str) -> list[str]:
    ctx = f"\n\nRelevant user context:\n{context}" if context else ""
    try:
        raw = await llm.cheap(
            [{"role": "system", "content":
              "Decompose the research topic into at most 5 focused sub-questions. "
              "Return ONLY a JSON array of strings."},
             {"role": "user", "content": f"{query}{ctx}"}],
            temperature=0.2, max_tokens=300, task="research_plan",
        )
        raw = _strip_fences(raw)
        arr = json.loads(raw[raw.find("["): raw.rfind("]") + 1])
        subqs = [s.strip() for s in arr if isinstance(s, str) and s.strip()][:MAX_SUBQUESTIONS]
        if subqs:
            return subqs
    except Exception:
        pass
    return [query, f"{query} overview", f"{query} analysis"]


# ── Phase 2+3: Search + ingest ─────────────────────────────────────────────────

def _chunk_text(text: str) -> list[str]:
    return [text[i:i + CHUNK_CHARS] for i in range(0, len(text), CHUNK_CHARS)][:CHUNKS_PER_PAGE]


async def _sub_agent(research_id: str, subq: str) -> list[dict]:
    """Search one sub-question (recency-aware via pipeline), chunk + embed + persist."""
    resp = await search.search(subq, max_results=RESULTS_PER_SUBQ,
                               top_k=RESULTS_PER_SUBQ, want_content=True)
    out: list[dict] = []
    for r in resp.results:
        url, title = r.url, r.title
        body = r.content or r.snippet
        if not body:
            continue
        published_at = r.published_at
        for piece in _chunk_text(body):
            vec = await embeddings.embed(piece)
            chunk_id = str(uuid.uuid4())

            def op(conn, cid=chunk_id, url=url, title=title, piece=piece, vec=vec):
                conn.execute(
                    "INSERT INTO research_chunk(id, research_id, url, title, text, fetched_at) "
                    "VALUES(?,?,?,?,?,?)",
                    (cid, research_id, url, title, piece, db.now()),
                )
                rid_ = conn.execute(
                    "SELECT rowid FROM research_chunk WHERE id=?", (cid,)
                ).fetchone()[0]
                conn.execute(
                    "INSERT INTO research_chunk_vec(rowid, embedding) VALUES(?,?)",
                    (rid_, db.serialize_f32(vec)),
                )

            await db.write(op)
            out.append({"id": chunk_id, "url": url, "title": title,
                        "text": piece, "vec": vec, "published_at": published_at})
    return out


# ── Phase 4: Gap analysis ──────────────────────────────────────────────────────

async def _gap_check(query: str, chunks: list[dict], asked: set[str]) -> dict:
    sample = "\n".join(c["text"][:300] for c in chunks[:8])
    try:
        raw = await llm.cheap(
            [{"role": "system", "content":
              "You are a research gap analyzer. Given a query and source excerpts, "
              "estimate how well the sources cover the topic and identify gaps. "
              "ALWAYS propose 2-4 new_sub_questions that would deepen the research or "
              "open an adjacent angle — even when coverage seems high, unless the topic "
              "is truly exhausted. Prefer questions not already asked. "
              'Return ONLY JSON: {"coverage":0.0,"new_sub_questions":[],"contradictions":[]}'},
             {"role": "user", "content": f"Query: {query}\n\nExcerpts:\n{sample}"}],
            temperature=0.3, max_tokens=400, task="research_gap",
        )
        raw = _strip_fences(raw)
        obj = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        new_qs = [
            q.strip() for q in (obj.get("new_sub_questions") or [])
            if isinstance(q, str) and q.strip() and q.strip() not in asked
        ][:MAX_SUBQUESTIONS]
        return {
            "coverage": float(obj.get("coverage", 0.5)),
            "new_sub_questions": new_qs,
            "contradictions": obj.get("contradictions", []),
        }
    except Exception:
        return {"coverage": 0.5, "new_sub_questions": [], "contradictions": []}


# ── Phase 5: Ranking ───────────────────────────────────────────────────────────

def _top_chunks(chunks: list[dict], query_vec: list[float], n: int) -> list[dict]:
    """Top-n chunks by similarity, but capped per domain so the evidence pool
    spans multiple independent sources (a prerequisite for corroboration)."""
    if not chunks:
        return []
    q = np.asarray(query_vec, dtype=np.float32)
    ranked = sorted(
        chunks,
        key=lambda c: float(np.dot(q, np.asarray(c["vec"], dtype=np.float32))),
        reverse=True,
    )
    out: list[dict] = []
    per_dom: dict[str, int] = {}
    for c in ranked:
        dom = _domain(c.get("url", ""))
        if per_dom.get(dom, 0) >= POOL_PER_DOMAIN:
            continue
        per_dom[dom] = per_dom.get(dom, 0) + 1
        out.append(c)
        if len(out) >= n:
            return out
    # Backfill from what the per-domain cap skipped, if we're short.
    if len(out) < n:
        chosen = {id(c) for c in out}
        for c in ranked:
            if id(c) not in chosen:
                out.append(c)
                if len(out) >= n:
                    break
    return out


# ── Phase 6: Claim synthesis ───────────────────────────────────────────────────

async def _synthesize_claims(query: str, chunks: list[dict], context: str) -> dict:
    ctx_section = f"\nPersonal context:\n{context}\n" if context else ""
    numbered = "".join(
        f"\n[{i}] {c['title']} ({c['url']})\n{c['text']}\n"
        for i, c in enumerate(chunks, 1)
    )
    system = (
        "You are a research analyst. Using ONLY the provided numbered sources, write a "
        "grounded report structured as atomic, checkable claims. "
        "Return ONLY a JSON object:\n"
        '{"title":"...","summary":"2-3 sentences",'
        '"sections":[{"title":"...","claims":['
        '{"text":"one atomic assertion","evidence_chunks":[1,2]}'
        ']}]}\n'
        "Each claim must cite EVERY chunk that supports it, not just one — if two "
        "or more sources back a claim, list all of them, and prefer claims that "
        "more than one source corroborates. "
        "Aim for 4-6 sections, 3-6 claims per section. Be specific."
    )
    raw = await llm.complete(
        [{"role": "system", "content": system},
         {"role": "user", "content": f"Topic: {query}{ctx_section}\n\nSources:{numbered}"}],
        temperature=0.3, task="research_synthesis",
    )
    raw = _strip_fences(raw)
    return json.loads(raw[raw.find("{"): raw.rfind("}") + 1])


# ── Phase 7: Verification ──────────────────────────────────────────────────────

def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc
    except Exception:
        return ""


async def _nli(claim_text: str, evidence_text: str) -> tuple[str, float]:
    """Cheap-model entailment: does the evidence support/refute/not-address the claim?"""
    try:
        raw = await llm.cheap(
            [{"role": "system", "content":
              "Does the evidence support, refute, or not address the claim? "
              'Return ONLY JSON: {"verdict":"supports|refutes|neutral","strength":0.0}'},
             {"role": "user", "content":
              f"Evidence: {evidence_text[:NLI_CONTEXT_CHARS]}\nClaim: {claim_text}"}],
            temperature=0.0, max_tokens=60, task="claim_verify",
        )
        raw = _strip_fences(raw)
        nli = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        return nli.get("verdict", "neutral"), float(nli.get("strength", 0.0))
    except Exception:
        return "neutral", 0.0


async def _verify_claim(
    claim_text: str,
    chunk_indices: list[int],
    chunks: list[dict],
) -> tuple[float, str, list[dict]]:
    """Return (confidence, stance, evidence_rows) for one claim.

    Two passes: (1) check the sources the writer actually cited; (2) if fewer than
    two independent supporting domains result, actively scan the rest of the
    evidence pool for a corroborating source from a *different* domain — so a claim
    the web genuinely backs can reach "supported" instead of stalling at
    "single_source" just because the writer only cited one source.
    """
    claim_vec = np.asarray(await embeddings.embed(claim_text), dtype=np.float32)
    evidence_rows: list[dict] = []
    supporting: list[float] = []
    refuting_count = 0
    domains: set[str] = set()
    used_chunk_ids: set[str] = set()

    # ── Pass 1: the writer's cited sources ──
    for idx in chunk_indices:
        if idx < 1 or idx > len(chunks):
            continue
        c = chunks[idx - 1]
        used_chunk_ids.add(c["id"])
        cos = float(np.dot(claim_vec, np.asarray(c["vec"], dtype=np.float32)))

        # Transparency: a citation too weakly related to count as evidence is kept
        # and shown (marked "set_aside"), not silently discarded.
        if cos < EVIDENCE_MIN_COS:
            evidence_rows.append({"chunk_id": c["id"], "url": c["url"],
                                  "published_at": c.get("published_at"),
                                  "entail": 0.0, "polarity": "set_aside"})
            continue

        verdict, strength = await _nli(claim_text, c["text"])
        polarity = "supports" if verdict == "supports" else (
            "refutes" if verdict == "refutes" else "neutral")
        evidence_rows.append({"chunk_id": c["id"], "url": c["url"],
                              "published_at": c.get("published_at"),
                              "entail": strength if polarity == "supports" else 0.0,
                              "polarity": polarity})
        if verdict == "supports":
            supporting.append(strength)
            domains.add(_domain(c["url"]))
        elif verdict == "refutes":
            refuting_count += 1

    # ── Pass 2: corroboration from independent domains ──
    if refuting_count == 0 and len(domains) < 2:
        cands: list[tuple[float, dict, str]] = []
        for c in chunks:
            if c["id"] in used_chunk_ids:
                continue
            dom = _domain(c["url"])
            if not dom or dom in domains:
                continue
            cos = float(np.dot(claim_vec, np.asarray(c["vec"], dtype=np.float32)))
            if cos >= CORROB_MIN_COS:
                cands.append((cos, c, dom))
        cands.sort(key=lambda t: t[0], reverse=True)

        checks = 0
        for cos, c, dom in cands:
            if len(domains) >= 2 or checks >= CORROB_MAX_CHECKS:
                break
            if dom in domains:
                continue
            checks += 1
            verdict, strength = await _nli(claim_text, c["text"])
            if verdict == "supports":
                evidence_rows.append({"chunk_id": c["id"], "url": c["url"],
                                      "published_at": c.get("published_at"),
                                      "entail": strength, "polarity": "supports"})
                supporting.append(strength)
                domains.add(dom)
                used_chunk_ids.add(c["id"])

    if not supporting and not refuting_count:
        return 0.0, "unverified", evidence_rows

    mean_entail = sum(supporting) / len(supporting) if supporting else 0.0
    diversity = min(1.0, len(domains) / 2)
    confidence = max(0.0, min(1.0,
        mean_entail * diversity - 0.25 * (refuting_count > 0)
    ))
    if refuting_count > 0:
        stance = "disputed"
    elif len(domains) <= 1:
        stance = "single_source"
    elif confidence >= 0.6 and len(domains) >= 2:
        stance = "supported"
    else:
        stance = "unverified"

    return confidence, stance, evidence_rows


# ── Phase 8: Entity graph ──────────────────────────────────────────────────────

async def _extract_entities(research_id: str, claims: list[dict]) -> None:
    if not claims:
        return
    claim_texts = "\n".join(f"- {c['text']}" for c in claims[:20])
    try:
        raw = await llm.cheap(
            [{"role": "system", "content":
              "Extract entities and relations from these research claims. "
              "Return ONLY JSON: "
              '{"entities":[{"name":"...","kind":"concept|metric|substance|condition|person|org"}],'
              '"relations":[{"src":"...","dst":"...","kind":"affects|increases|decreases|correlates|contradicts"}]}'},
             {"role": "user", "content": claim_texts}],
            temperature=0.2, max_tokens=800, task="research_gap",
        )
        raw = _strip_fences(raw)
        obj = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
    except Exception:
        return

    entities_raw = (obj.get("entities") or [])[:30]
    relations_raw = (obj.get("relations") or [])[:40]
    ts = db.now()
    name_to_id: dict[str, str] = {}

    def op(conn):
        for e in entities_raw:
            name = str(e.get("name", "")).strip()[:120]
            if not name:
                continue
            eid = str(uuid.uuid4())
            name_to_id[name.lower()] = eid
            conn.execute(
                "INSERT INTO entity(id, research_id, name, kind, created_at) VALUES(?,?,?,?,?)",
                (eid, research_id, name, e.get("kind"), ts),
            )
        for rel in relations_raw:
            src = str(rel.get("src", "")).strip()
            dst = str(rel.get("dst", "")).strip()
            if not src or not dst:
                continue
            src_id = name_to_id.get(src.lower())
            dst_id = name_to_id.get(dst.lower())
            if not src_id or not dst_id:
                continue
            conn.execute(
                "INSERT INTO relation(id, research_id, src_entity, dst_entity, kind, created_at)"
                " VALUES(?,?,?,?,?,?)",
                (str(uuid.uuid4()), research_id, src_id, dst_id, rel.get("kind"), ts),
            )

    await db.write(op)


# ── Main job ───────────────────────────────────────────────────────────────────

@jobs.register("research")
async def run_research(payload: dict):
    research_id = payload["research_id"]
    entry = await research_repo.get(research_id)
    if not entry:
        return
    query = entry["query"]
    start_ts = time.time()
    store = get_store(research_id)

    async def push(phase: str, **data: object) -> None:
        await store.push(phase, **data)

    try:
        # Clear any partial output from a prior attempt so re-runs are idempotent.
        await research_repo.reset_progress(research_id)

        # [0] Personal context
        context = await _get_context(query)
        await push("planning")

        # [1] Initial sub-questions
        subqs = await _plan(query, context)
        asked: set[str] = set(subqs)
        all_chunks: list[dict] = []
        examined_urls: set[str] = set()
        total_subq = len(subqs)
        rounds_completed = 0

        await push("round", round=1, sub_questions=subqs)

        for round_num in range(1, MAX_ROUNDS + 1):
            if not subqs:
                break
            rounds_completed = round_num

            # [2+3] Parallel search + ingest
            gathered = await asyncio.gather(*[_sub_agent(research_id, sq) for sq in subqs])
            all_chunks.extend(c for sub in gathered for c in sub)
            examined_urls.update(c["url"] for c in all_chunks if c.get("url"))
            # Honest counts: distinct sources vs. raw passages (3 passages/page).
            await push("sources_found", count=len(examined_urls),
                       passages=len(all_chunks), round=round_num)

            # [4] Gap check
            gap = await _gap_check(query, all_chunks, asked)
            remaining = max(0, MAX_TOTAL_SUBQ - total_subq)
            new_qs = gap.get("new_sub_questions", [])[:remaining]

            # Stop only when out of questions/budget, at MAX_ROUNDS, or coverage is
            # met AND we've already done the minimum depth. The MIN_ROUNDS floor is
            # what stops a lazy gap-check from ending the whole job after one round.
            hit_target = gap["coverage"] >= COVERAGE_TARGET and round_num >= MIN_ROUNDS
            if not new_qs or round_num == MAX_ROUNDS or hit_target:
                break

            subqs = new_qs[:MAX_SUBQUESTIONS]
            asked.update(subqs)
            total_subq += len(subqs)
            await push("round", round=round_num + 1, sub_questions=subqs)

        # [5] Rank top chunks
        query_vec = await embeddings.embed(query)
        top = _top_chunks(all_chunks, query_vec, SYNTH_CHUNKS)
        if not top:
            await research_repo.mark_error(research_id, "No web sources could be fetched.")
            await push("error", message="No web sources could be fetched.")
            return

        # [6] Claim synthesis
        await push("synthesizing")
        try:
            report = await _synthesize_claims(query, top, context)
        except Exception:
            # Fall back to plain synthesis if structured claims fail
            report = {"title": query, "summary": "", "sections": [], "key_findings": []}

        # Distinct cited sources in ranked order. Persist now so the Sources
        # panel populates live while the report is still being written.
        seen_urls: set[str] = set()
        sources: list[dict] = []
        for c in top:
            if c["url"] and c["url"] not in seen_urls:
                seen_urls.add(c["url"])
                sources.append({"url": c["url"], "title": c["title"]})
        await research_repo.save_sources(research_id, sources)

        # [7] Verify claims; persist each section + its claims incrementally so a
        # reload (or navigating away and back) renders from DB truth, not from
        # ephemeral stream state.
        sections_for_db: list[dict] = []
        high_confidence_claims: list[str] = []
        all_verified: list[dict] = []

        for sec_idx, sec in enumerate(report.get("sections", [])):
            verified_claims: list[dict] = []
            for raw_claim in sec.get("claims", []):
                claim_text = raw_claim.get("text", "")
                if not claim_text:
                    continue
                confidence, stance, evidence_rows = await _verify_claim(
                    claim_text, raw_claim.get("evidence_chunks", []), top
                )
                await research_repo.add_claim(
                    research_id, claim_text, sec_idx, confidence, stance, evidence_rows
                )
                verified_claims.append(
                    {"text": claim_text, "confidence": confidence, "stance": stance})
                all_verified.append({"text": claim_text})
                await push("claim_verified", claim=claim_text,
                           confidence=confidence, stance=stance)

                if confidence >= 0.6 and stance in ("supported", "single_source"):
                    high_confidence_claims.append(claim_text)

            content = " ".join(c["text"] for c in verified_claims)
            sec_title = sec.get("title", "")
            sections_for_db.append({"title": sec_title, "content": content})
            await research_repo.upsert_section(research_id, sec_idx, sec_title, content)
            await push("section_ready",
                       section={"title": sec_title, "content": content})

        # [8] Entity graph
        await _extract_entities(research_id, all_verified)

        # [9] Finalize report (title/summary/status/stats). Sections + claims are
        # already persisted; save_result rewrites sections idempotently.
        elapsed = round(time.time() - start_ts)
        await research_repo.save_result(
            research_id,
            title=report.get("title", query),
            summary=report.get("summary", ""),
            sections=sections_for_db,
            sources=sources,
            stats={
                "Duration": f"{elapsed}s",
                "Rounds": rounds_completed,
                "Claims": len(all_verified),
                "Cited": len(sources),
                "Examined": len(examined_urls),
            },
        )

        # Push high-confidence claims to the shared memory substrate
        for finding in (high_confidence_claims or report.get("key_findings", [])):
            if isinstance(finding, str) and finding.strip():
                await memory.add_atom(
                    text=finding.strip(), type_="fact",
                    source_kind="research", source_id=research_id, dedup=True,
                )

        await push("done", as_of=int(time.time()))

    except Exception as e:  # noqa: BLE001
        await research_repo.mark_error(research_id, str(e))
        await push("error", message=str(e))
        raise
