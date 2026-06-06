"""Metrics endpoint (Part 1.7 / Part 4) — p50/p95/p99 per path, job timings,
queue depth, and memory atom count."""
from __future__ import annotations

from fastapi import APIRouter

from services import memory, metrics, search
from workers import jobs

router = APIRouter(prefix="/api")


@router.get("/metrics")
async def get_metrics():
    return {
        "requests": metrics.summary(),
        "jobs": await metrics.job_summary(),
        "queue": await jobs.stats(),
        "memory_atoms": await memory.count(),
        "search": await search.metrics_summary(),
    }
