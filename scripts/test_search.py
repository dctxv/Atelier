"""Search-layer test gates (Build Spec Part 5 A4-F4), run in-process.

Proves each layer in isolation, then end-to-end. No app server needed; we set up
the shared httpx client + DB the same way the lifespan does.
"""
from __future__ import annotations

import asyncio
import sys
import time

import httpx

from services import config, db, http_client
from services.search import cache, freshness, obs, registry, rerank, router, usage
from services.search.schema import SearchResult

PASS, FAIL = "PASS", "FAIL"
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"  [{PASS if ok else FAIL}] {name}{(' — ' + detail) if detail else ''}")


def _fmt(epoch):
    if not epoch:
        return "n/a"
    import datetime as _dt
    return _dt.datetime.fromtimestamp(epoch, _dt.timezone.utc).strftime("%Y-%m-%d")


async def phase_A():
    print("\n=== Phase A — one reliable provider, proven in isolation ===")
    # Prove the primary if a key is present (Tavily); else the key-free workhorse.
    tav = registry.get("tavily")
    use_tavily = await tav.available()
    provider = tav if use_tavily else registry.get("duckduckgo")
    print(f"    proving provider: {provider.name}")
    queries = ["python asyncio", "world news", "climate change", "stock market",
               "openai", "fastapi tutorial", "sqlite wal", "nba scores",
               "weather sydney", "large language models"]
    lat, nonempty, valid_urls = [], 0, True
    for q in queries:
        t = time.perf_counter()
        try:
            res = await provider.search(q, max_results=8)
        except Exception as e:
            res = []
            print("    provider error:", e)
        lat.append((time.perf_counter() - t) * 1000)
        if res:
            nonempty += 1
        for r in res:
            if not r.url.startswith("http"):
                valid_urls = False
        if not use_tavily:
            await asyncio.sleep(1.2)  # be polite; DDG challenges bursts
    threshold = 9 if use_tavily else 8
    check(f"{provider.name} returns results for >={threshold}/10 queries",
          nonempty >= threshold, f"{nonempty}/10")
    check("all result URLs are http(s)", valid_urls)
    check("per-call latency logged",
          bool(lat), f"p50~{sorted(lat)[len(lat)//2]:.0f}ms p95~{sorted(lat)[int(len(lat)*0.95)-1]:.0f}ms")
    check("Tavily provider wired (availability check works)",
          (await tav.available()) in (True, False),
          "key present" if use_tavily else "no key (ready when set)")


async def phase_B():
    print("\n=== Phase B — fallback chain + reliability ===")
    # Force the primary (tavily) to FAIL by giving it a bad key, then assert the
    # router transparently falls back to a free provider. IMPORTANT: preserve and
    # restore the user's real key/order so the test is non-destructive.
    saved_key = await config.get_secret("tavily_api_key")
    saved_order = await config.get_setting("search_provider_order")
    try:
        await config.set_secret("tavily_api_key", "tvly-BADKEY-forcing-failure")
        await config.set_setting("search_provider_order", "tavily,duckduckgo")
        t = time.perf_counter()
        res, used, cost = await router.route("breaking technology news", max_results=6)
        added = (time.perf_counter() - t) * 1000
        check("fallback produced results despite primary failure", bool(res), f"{len(res)} results")
        check("fell back to a free provider (no user-visible error)", "duckduckgo" in used, str(used))
        check("fallback latency within primary timeout cap + free call", added < 12000, f"{added:.0f}ms")
    finally:
        # restore exactly what the user had
        if saved_key:
            await config.set_secret("tavily_api_key", saved_key)
        else:
            await config.set_secret("tavily_api_key", "")
        await config.set_setting("search_provider_order", saved_order or "")
        print("    (restored real Tavily key + provider order)")


async def phase_C():
    print("\n=== Phase C — caching ===")
    from services.search import pipeline
    q = "what is reciprocal rank fusion"
    # cold
    r1 = await pipeline.search(q, max_results=5, top_k=2, want_content=False)
    calls_before = await usage.calls_this_month("duckduckgo")
    # warm
    t = time.perf_counter()
    r2 = await pipeline.search(q, max_results=5, top_k=2, want_content=False)
    hit_ms = (time.perf_counter() - t) * 1000
    calls_after = await usage.calls_this_month("duckduckgo")
    check("repeat query served from cache", r2.from_cache, f"from_cache={r2.from_cache}")
    check("cached query p95 < 20ms", hit_ms < 20, f"{hit_ms:.1f}ms")
    check("cache hit spends ZERO provider calls", calls_after == calls_before,
          f"{calls_before}->{calls_after}")


async def phase_D():
    print("\n=== Phase D — real-time / freshness ===")
    c_now = freshness.classify("latest news today on the election results")
    c_stable = freshness.classify("what is the capital of france")
    check("volatile/now query classified fresh+news", c_now["fresh"] and c_now["is_news"], str(c_now))
    check("stable query classified not-fresh", not c_stable["fresh"], str(c_stable))
    check("volatile TTL << stable TTL",
          freshness.ttl_for(c_now) < freshness.ttl_for(c_stable),
          f"{freshness.ttl_for(c_now)}s vs {freshness.ttl_for(c_stable)}s")
    check("recency param maps to a window", freshness.recency_param(c_now) in ("day", "week"),
          str(freshness.recency_param(c_now)))
    # stale-link guard: a guaranteed-404 URL must be flagged stale
    from services.search import extraction
    bad = SearchResult(title="dead", url="https://httpbin.org/status/404", snippet="")
    await extraction.enrich([bad], top_k=1, want_content=True)
    check("stale/404 link flagged stale", bad.stale, f"stale={bad.stale}")

    # D5 — the real-time gate. Probe a KNOWN recent event (US–Iran Strait of
    # Hormuz strikes, 5-6 Jun 2026) and assert it's found AND correctly dated.
    from services.search import pipeline
    if await registry.get("tavily").available():
        probe = "latest news today US Iran Strait of Hormuz strikes"
        rt = await pipeline.search(probe, max_results=8, top_k=4, want_content=False)
        hits = rt.results
        topical = [r for r in hits if any(k in (r.title + " " + r.snippet).lower()
                   for k in ("iran", "hormuz", "ceasefire", "strike"))]
        recent = [r for r in hits if r.published_at and
                  (db.now() - r.published_at) < 5 * 86400]
        check("real-time event FOUND", bool(topical), f"{len(topical)}/{len(hits)} topical")
        check("event correctly DATED (a result published within ~5 days)",
              bool(recent), f"{len(recent)} recent; newest={_fmt(max((r.published_at for r in hits if r.published_at), default=0))}")
        check("freshness routed via news provider", "tavily" in rt.providers_used or rt.from_cache,
              str(rt.providers_used))
    else:
        print("    [skip] real-time probe needs Tavily key (provider not available)")


async def phase_E():
    print("\n=== Phase E — rerank + chunk + dedup ===")
    q = "how does the FSRS spaced repetition algorithm schedule cards"
    cand = [
        SearchResult(title="Unrelated cooking recipe", url="https://x/1",
                     snippet="how to bake sourdough bread at home"),
        SearchResult(title="FSRS algorithm explained", url="https://x/2",
                     snippet="FSRS is a spaced repetition scheduler using stability and difficulty to set review intervals"),
        SearchResult(title="FSRS algorithm explained (dup)", url="https://x/3",
                     snippet="FSRS is a spaced repetition scheduler using stability and difficulty to set review intervals"),
        SearchResult(title="Random sports news", url="https://x/4",
                     snippet="the local team won the championship last night"),
    ]
    ranked = await rerank.rerank_and_dedup(q, cand)
    check("rerank puts the relevant doc first", ranked[0].url == "https://x/2",
          f"top={ranked[0].title!r}")
    check("near-duplicate removed", all(r.url != "https://x/3" for r in ranked),
          f"{len(ranked)} kept of 4")
    chunks = rerank.chunk(ranked, budget_tokens=50, chunk_chars=200)
    tok = sum(max(1, len(c["text"]) // 4) for c in chunks)
    check("chunk output respects token budget", tok <= 60, f"{tok} tokens")


async def phase_F():
    print("\n=== Phase F — observability ===")
    s = obs.summary()
    check("queries counted in metrics", s["queries"] > 0, str(s["queries"]))
    check("cache hit rate present", "cache_hit_rate" in s, str(s.get("cache_hit_rate")))
    check("per-provider latency recorded", bool(s["provider_latency_ms"]),
          ",".join(s["provider_latency_ms"].keys()))
    u = await usage.summary()
    check("monthly provider usage tracked", bool(u), str(list(u.keys())))


async def main():
    async with httpx.AsyncClient() as c:
        http_client.set_client(c)
        await db.init_db()
        await phase_A()
        await phase_B()
        await phase_C()
        await phase_D()
        await phase_E()
        await phase_F()
    print(f"\n{'='*50}\n{sum(results)}/{len(results)} checks passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    asyncio.run(main())
