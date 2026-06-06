# Web search

*The search layer: query in → ranked, fresh, deduped results out. Cheap, fast, real-time. Written by Clay.*

---

## Why this exists

Research, quick lookups, and chat grounding all need the same thing underneath: given a query, get back *excellent* web results — fresh, deduplicated, ranked, optionally with clean extracted text. So I built that one thing properly and made everything else sit on top of it. This layer's only job is to produce great results; what *reads* them (the research synthesiser, a chat reply) is a separate concern.

The headline requirement was **real-time events** — minute/hour-fresh — while keeping cost and latency down. The v1 research code scraped DuckDuckGo and SearXNG, and honestly it barely worked. This replaces it.

## The seven layers

A request flows down; results flow back up. Each layer is small and independently testable (`services/search/`):

```
query
 → [1] freshness classifier   freshness.py   is it time-sensitive? what window? news?
 → [2] cache lookup           cache.py       TTL-valid hit returns instantly, zero cost
 → [3] provider router        router.py      ordered fallback chain, per-provider timeout, budget
 → [4] providers              providers/     Tavily | Brave | SearXNG | DuckDuckGo (uniform interface)
 → [5] extraction + guard     extraction.py  clean content + published_at + stale-link flag
 → [6] rerank + dedup + chunk rerank.py      local-embedding rerank, near-dup removal, token budget
 → [7] output contract        schema.py      SearchResult / SearchResponse
```

`pipeline.py` is the orchestrator; `search(query, ...)` is the one function consumers call.

## The output contract

Consumers read this and nothing else, so swapping a provider never changes what they see:

```
SearchResult  { title, url, snippet, content?, published_at?, score, source_provider, stale }
SearchResponse{ query, results[], as_of, providers_used[], cost_units, from_cache }
```

## Providers (cost-minimal, real-time-capable)

Everything is behind a uniform `SearchProvider` interface, so adding or reordering providers is config, not code surgery (`registry.py`, fallback order in `app_config`).

- **Tavily — primary.** LLM-native: one round-trip returns scored results plus optional `raw_content`, and `topic=news` + `time_range`/`days` gives real-time. `search_depth=basic` keeps latency ~1s. Free 1,000/mo. This is the recommended setup and what makes the real-time gate pass cleanly.
- **DuckDuckGo — zero-cost fallback.** No key, no quota. It's *best-effort*: DDG aggressively rate-limits automated access and answers bursts with a 202 "anomaly" challenge, so the provider retries with backoff, rotates user-agents, and tries multiple endpoints. Good enough to keep the lights on with no key; not something to lean on for volume. DDG gives no publish dates, so the freshness guard derives them from page metadata.
- **SearXNG — zero-cost fallback.** Self-hosted (free, private, no key). Off unless an instance is reachable (`SEARXNG_INSTANCE`).
- **Brave — optional paid upgrade.** Independent index, lowest latency, Brave News for minute-level recency. Off unless a key is set.

Keys are stored **encrypted**, the same Fernet path as the model endpoint keys (`config.set_secret`/`get_secret`) — never plaintext.

## The parts that matter

- **Cache first.** A repeated query costs zero provider calls and returns in ~1ms. `search_cache` is keyed on the normalized query + a params hash (recency/provider/depth), writes go through the single-writer executor, and TTL is **volatility-aware**: volatile (prices/scores) → 5 min, news → 15 min, fresh → 1 h, stable → 24 h. This is the single biggest cost *and* latency lever.
- **Freshness is rules-based, not a model.** The classifier (`freshness.py`) is regex over time signals ("today/latest/now", prices/scores, event verbs like "strikes/ceasefire/election", recent years). It runs in well under a millisecond, so it adds nothing to the hot path, and it drives both the provider recency params and the cache TTL.
- **The stale-link guard.** Tavily can serve stale/404 links from its cache. For the top-K I fetch the page once and get three things from that one fetch: clean content (when the provider didn't give `raw_content`), `published_at` (from `article:published_time` / JSON-LD / `<time>` — this is what dates results from providers that don't), and a `stale` flag for dead links. Jina Reader is the fallback extractor for JS-heavy pages.
- **Local rerank, never a paid reranker.** Candidates are embedded with the v1 local embeddings (cached, zero marginal cost) and ordered by cosine similarity to the query; near-duplicates (same vector) are dropped; chunks are capped to a token budget.
- **Budgets enforced in code.** A per-query provider-call budget (≤4), a generous primary timeout that guards against a *hanging* provider without cancelling a normally-slow one, and a monthly quota tracker (`search_provider_usage`) that makes the router skip a provider near its free-tier cap and fall back automatically — so a free-tier cap is never silently exceeded.

## How it's wired in

- **Chat grounding.** A **Web** toggle sits to the right of the model picker in the composer. When it's on, the chat router runs `search()` on the message (fast synchronous path), injects the top results into the system prompt exactly like skills/memory, and — so the UI can show *exactly* what was searched — streams a `atelier_search` event (the real query + real sources) before the model's tokens. The chat surface renders that as a collapsible "Searching the web" trace with favicons, titles, domains, and dates. No placeholders: if a source has no date, it shows none.
- **Research.** `workers/research.py` calls the same `search()` per sub-question (with `want_content=True`), so research now gets caching, reranking, freshness, and the stale guard for free.
- **Setup.** `/setup search` (or double-clicking the Web toggle) opens a panel to paste a Tavily/Brave key or continue keyless. `/setup model` still configures the AI endpoint. Keys are saved via `PUT /api/search/keys` (encrypted).
- **Metrics.** Per-provider p50/p95 latency, cache-hit rate, freshness coverage, cost units, and monthly usage all land in `/api/metrics` under `search` (and `GET /api/search/metrics`).

## Proving it (test gates)

`scripts/test_search.py` runs the whole thing in-process and is non-destructive (it saves and restores the real Tavily key around the fallback test). With a Tavily key, all 25 checks pass, including:

- **Real-time (the important one):** probe a known event from the last 24–48 h (the US–Iran Strait of Hormuz strikes) → found, 8/8 topical, correctly dated to today, routed via Tavily news.
- Cached query < 20 ms (measured ~1 ms) spending **zero** provider calls.
- Primary failure (bad key) falls back to a free provider with no user-visible error.
- Volatile vs stable queries get short vs long TTLs; a 404 link is flagged stale.
- Rerank beats raw provider order; near-duplicates removed; chunks respect the token budget.
- Tavily p50 ~1.0 s / p95 ~1.5 s.

## Bugs I fixed after the initial build

### The freshness classifier missed "most recent" and "current"

The first version of the classifier had `_NOW` covering `today`, `latest`, `right now`, `just now`, `breaking`, `currently`, and a few time-of-day phrases. Reasonable for breaking news, but it missed the broader class of "tell me what's happening now" queries that use words like "recent", "most recent", "newest", "current state of", "up to date", "this year".

A query like "What is the most recent innovation for AI?" would therefore reach the provider with no recency parameters — no `topic=news`, no `days=3` — and Tavily would return evergreen pages ranked by relevance, not freshness. In practice this meant a 2024 article about "How AI is Accelerating Innovation" coming back as the top result when the user wanted something from this week.

The fix was to expand `_NOW` to include `recent(ly)?`, `newest`, `most recent`, `current`, `up-to-date`, `this year`, and `in [year]`:

```python
_NOW = re.compile(
    r"\b(today|tonight|right now|just now|breaking|latest|newest|most recent|"
    r"recent(ly)?|currently|current|live|"
    r"this (morning|afternoon|evening|week)|as of|update[sd]?|"
    r"in \d{4}|this year|up.?to.?date)\b", re.I)
```

Now "most recent AI innovation" classifies as `fresh=True, window=day, is_news=True` and Tavily returns this week's results.

### The model was ignoring injected results and claiming no web access

After the search ran and the results were injected, the model would sometimes reply: "I don't have real-time access to the latest AI news, so I can't give you today's most recent breakthrough. My knowledge has a cutoff date…" — and then summarise information from its training data instead of the injected results.

The root cause is that models are trained to say this. It's baked into their RLHF tuning as a responsible response. A mild framing like `[WEB SEARCH] Live results (cite the URLs when you use them):` wasn't strong enough to override that trained default.

The fix was to make the header explicitly contradictory to the model's training reflex:

```
[WEB SEARCH (fetched 2026-06-06)] You have live web results below.
Answer directly from them. Do NOT say you lack web access, have a knowledge
cutoff, or cannot browse — you are looking at real search results right now.
Cite the source URLs inline.
```

The key phrases are "You have live web results" (not "here are some results"), "Answer *directly* from them" (not "you can reference these"), and the explicit prohibition of the disclaimer. This works consistently across the models I've tested.

The broader point: injected context only works if the framing makes it unmistakably authoritative. A results block that reads like an appendix will be treated like one. A block that reads like the model's *actual* current knowledge will be treated that way instead.

---

## What I didn't build (this layer's scope ends here)

Out of scope on purpose — these *consume* the layer and come later as their own spec: research synthesis, multi-mode routing (academic/code/deep), report writing, citations-in-prose. This layer only has to produce excellent search results. It now does, and it's a dependable primitive the research agent can be built on.

A few smaller deferrals: Firecrawl as a second extraction fallback (Jina covers it for now), a UI for reordering the provider chain (it's config today), and escalating Tavily to `advanced` depth on explicit deep requests (a downstream decision, not this layer's default).
