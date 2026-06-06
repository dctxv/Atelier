"""Latency + concurrency benchmark (Part 4.3).

Fires a fixed workload at the running server with asyncio + httpx, collects
durations, prints p50/p95/p99. Also runs a concurrent-writer test that asserts
zero "database is locked" errors.

Usage (server must be running):
    python -m scripts.bench
    python -m scripts.bench --retrieval-only
"""
from __future__ import annotations

import argparse
import asyncio
import time

import httpx

BASE = "http://127.0.0.1:8000"


def _pcts(durations: list[float]) -> str:
    s = sorted(durations)
    n = len(s)
    def p(q):
        return s[min(n - 1, int(round(q / 100 * (n - 1))))]
    return f"n={n} p50={p(50):.1f}ms p95={p(95):.1f}ms p99={p(99):.1f}ms max={s[-1]:.1f}ms"


async def bench_retrieval(client: httpx.AsyncClient, iterations: int = 200):
    queries = ["what shell does Clay use", "how is the database built", "FSRS scheduling",
               "research fan-out", "share token expiry", "the hot path rules"]
    durations = []
    for i in range(iterations):
        q = queries[i % len(queries)]
        t = time.perf_counter()
        r = await client.post(f"{BASE}/api/memory/search", json={"query": q, "k": 12})
        r.raise_for_status()
        durations.append((time.perf_counter() - t) * 1000)
    print(f"[retrieval /api/memory/search]  {_pcts(durations)}")


async def bench_concurrent_writers(client: httpx.AsyncClient, writers: int = 40, each: int = 10):
    errors = []

    async def writer(w: int):
        for i in range(each):
            try:
                kind = i % 3
                if kind == 0:
                    r = await client.post(f"{BASE}/api/memory", json={"text": f"concurrent atom {w}-{i}"})
                elif kind == 1:
                    r = await client.post(f"{BASE}/api/notes", json={"title": f"n{w}-{i}", "body": "x"})
                else:
                    r = await client.post(f"{BASE}/api/tasks", json={"title": f"t{w}-{i}"})
                if r.status_code >= 500:
                    errors.append(f"{r.status_code}: {r.text[:120]}")
            except Exception as e:  # noqa: BLE001
                errors.append(str(e))

    t = time.perf_counter()
    await asyncio.gather(*[writer(w) for w in range(writers)])
    elapsed = (time.perf_counter() - t) * 1000
    total = writers * each
    locked = [e for e in errors if "locked" in e.lower()]
    print(f"[concurrency]  {total} overlapping writes in {elapsed:.0f}ms; "
          f"errors={len(errors)} db-locked={len(locked)}")
    if locked:
        print("  !! LOCK ERRORS:", locked[:3])


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--retrieval-only", action="store_true")
    args = ap.parse_args()
    async with httpx.AsyncClient(timeout=30) as client:
        await bench_retrieval(client)
        if not args.retrieval_only:
            await bench_concurrent_writers(client)
        m = (await client.get(f"{BASE}/api/metrics")).json()
        print(f"[server] memory_atoms={m['memory_atoms']} queue={m['queue']}")


if __name__ == "__main__":
    asyncio.run(main())
