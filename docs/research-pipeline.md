# Deep research

*Planner → parallel sub-agents → grounded synthesis → memory. Written by Clay.*

---

## What it does

I type a query; the Atelier produces a structured, source-grounded report and — crucially — pushes the key findings into shared memory so chat knows them afterward. It runs entirely as a background job (`workers/research.py`), so it uses the job system and has no hot-path budget.

The pipeline:

```
planner (cheap model)         → ≤5 focused sub-questions
sub-agents (asyncio.gather)   → search each sub-question IN PARALLEL
  → fetch top results (cached by URL)
  → chunk + embed into research_chunk(+_vec)
rank chunks by similarity to the query
synthesizer (big model)       → grounded report (JSON: title, summary, sections, findings)
persist report + a plain source list (URLs)
push key findings → memory (source_kind="research")
```

## The parts that matter

- **Parallel fan-out.** The sub-agents run under one `asyncio.gather`, so total time ≈ the *slowest* sub-agent + synthesis, not the sum. This is the single most important property of the phase — serial fan-out would make five sub-questions five times slower for no reason — so it's an explicit thing I check.
- **A real search backend.** Research no longer scrapes search engines itself — it calls the dedicated **search layer** ([web-search.md](web-search.md)) once per sub-question, so it inherits caching, freshness, the provider fallback chain (Tavily primary, DuckDuckGo/SearXNG free fallbacks), local rerank, and the stale-link guard for free. Research genuinely can't be "working" without a search backend, so this is a prerequisite, not an afterthought.
- **Grounding.** The synthesizer is told to use *only* the provided source chunks. The report ships with a plain list of source URLs. The chunks themselves are ranked against the query embedding (in memory, since we just embedded them) so the synthesizer sees the most relevant material first.
- **Findings → memory.** Each key finding becomes an atom (deduped), so a week later chat can use what the research found without me re-running anything. That's the integration model paying off.

The frontend reads a flat `raw_report` string, so the router renders the structured summary + sections into markdown for display while keeping the structured data in the tables.

---

## What I didn't build (v1)

- **Claim cards / contradiction detection** — breaking the report into individual verifiable claims, each with evidence and a confidence split, and flagging where sources disagree. This is the big v2 "Provenance Layer / Analyst Mode" and it's recorded in [v2-deferred.md](v2-deferred.md).
- **Inline citations** linking report sentences to specific sources. v1 has a source list, not footnotes.
- **Iterative deepening** — letting the planner spawn follow-up sub-questions based on what the first round found. v1 is a single planning pass.
- **Re-run / refine from the UI.** Delete and re-query for now.
