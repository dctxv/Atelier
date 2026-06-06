# Latency & bottleneck testing

*A first-class deliverable, not an afterthought. Written by Clay.*

---

## Why this is its own document

I decided early that I would not optimize anything I hadn't measured, and I would not declare a phase "done" until I'd measured what it added. So the instrumentation got built in Phase 0, before any feature, and every path has a budget I can check against. This doc records the harness and — more usefully — the bottlenecks I actually found, because the *process* is the point.

## The instrumentation

- **Timing middleware** records `path, method, status, duration_ms` for every `/api` and `/share` request into in-memory rolling buffers (not a DB write per request — see [shared-core.md](shared-core.md#7-instrumentation) for why).
- **Job timing** records `type, duration_ms, queue_wait_ms` for every background job.
- **`GET /api/metrics`** returns p50/p95/p99 per path, job timings, queue depth, and the live memory-atom count.

## The harness (`scripts/`)

- **`seed_memory.py N`** — inserts N synthetic atoms with embeddings (local hashing backend, so it's fast and offline) for the scaling test. Batched through the single writer.
- **`bench.py`** — fires a fixed workload with asyncio + httpx, collects durations, prints p50/p95/p99. Includes a concurrency test that launches overlapping writers and asserts zero lock errors.

## The targets

| Path | Target p95 |
|---|---|
| API + auth overhead (middleware) | < 5 ms |
| DB write (single statement, WAL) | < 10 ms |
| Local embed of one query | < 40 ms GPU / < 120 ms CPU |
| Memory retrieval @ 50k atoms | < 80 ms |
| Chat app-overhead before first token | < 50 ms |
| Co-writer first token | < 300 ms |
| Share download validation | < 50 ms |

---

## What I actually measured (50k atoms)

Seeded to **50,003 atoms**, then ran the bench against the live server.

**First run — retrieval p95 = 120ms. Over budget.** That's the whole reason you test before you have a problem. So I profiled the components instead of guessing:

```
embed query        : ~2 ms
vector_hits (vec0) : ~45 ms
fts_hits (normal)  : ~5 ms
fts_hits (common words "the", "project") : ~55 ms   ← surprise
full retrieve      : ~64 ms normal, ~123 ms with common words
```

Two findings, both counter to my assumptions:

1. **The vector scan was *not* the dominant cost.** A pure float32 256-dim brute-force scan over 50k vectors is ~14ms in isolation. So the spec's suggested "switch to int8" lever would have bought almost nothing — I'd have spent effort on the wrong thing. I left vectors as float32.
2. **Stopwords in the FTS query were a real cost.** Common words match a huge fraction of rows, and bm25 has to rank all of them. The vector side already covers semantics, so I strip stopwords from the keyword query.

The other easy win: the vector scan, the FTS scan, and the pinned lookup are independent, so I run them concurrently with `asyncio.gather` over the WAL read pool instead of summing them.

**After both fixes — retrieval p95 = 49ms at 50k atoms.** Comfortably under the 80ms budget.

```
[retrieval /api/memory/search]  n=200 p50=46.5ms p95=49.4ms p99=51.4ms max=61.8ms
```

### Middleware overhead

Across the simple GET endpoints, request overhead sits around **p95 ≈ 1–2ms** — well under the 5ms target. The in-memory metrics buffer (rather than a per-request DB write) is what keeps it there.

### Concurrency / write contention

The headline worry with SQLite. I fired **400 overlapping writes** — memory adds, note autosaves, and task creations all interleaved:

```
[concurrency]  400 overlapping writes in 585ms; errors=0 db-locked=0
```

**Zero lock errors.** The single-writer executor (one thread = one connection = serialized writes) holds under concurrency, which is exactly what it's for.

---

## Bottlenecks I'm still watching

- **Embedding throughput / job backlog** under sustained chat — watch `job_timing.queue_wait_ms` and queue depth. The local embedding backend is microseconds, so the real risk is the cheap-model extraction call; if it can't keep up I'll batch or throttle.
- **Research fan-out staying parallel** — the property to guard is that 5 sub-questions ≈ 1 sub-question + synthesis, not 5×.
- **Cold model load** — measured separately from steady state so it doesn't pollute percentiles.
- **SSE buffering through a tunnel** — `X-Accel-Buffering: no` is set; time-to-first-token needs re-checking once anything sits in front of the app.

## Acceptance

At 50k atoms with the seeded workload, every measured path meets its p95 target and concurrent writes produce no lock errors. The research fan-out is parallel by construction (`asyncio.gather`). That's the Part 4 acceptance bar, met.
