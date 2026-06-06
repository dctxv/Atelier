"""The Atelier — FastAPI entrypoint (thin).

Everything substantive lives in services/ and workers/. This file only wires
the app: lifespan (shared httpx client, DB init, importer, job system), the
timing + auth middleware, locked CORS, routers, and the static mount.
"""
from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from services import auth, db, http_client, importer, metrics
# Importing these modules registers their job handlers with the queue.
from workers import cards, cowriter, email as email_worker, extraction, jobs, research  # noqa: F401
from routers import (
    auth as auth_router,
    chat,
    config as config_router,
    cowriter as cowriter_router,
    email as email_router,
    files,
    flashcards,
    mcp as mcp_router,
    memory,
    metrics as metrics_router,
    notes,
    research as research_router,
    search as search_router,
    skills,
    tasks,
    web,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One shared httpx client for the whole app lifespan (hot-path rule 5).
    client = httpx.AsyncClient(timeout=30)
    http_client.set_client(client)

    await db.init_db()
    report = await importer.run_import()
    if report:
        print(f"[importer] migrated JSON -> SQLite: {report}")

    extraction.register_schedule()
    email_worker.register_schedule()
    await jobs.start()

    yield

    await jobs.stop()
    await metrics.flush_pending()
    await client.aclose()
    db.shutdown()


app = FastAPI(title="The Atelier", lifespan=lifespan)

# Lock CORS to real client origins (Part 1.6) — never "*" with credentials.
_origins = os.getenv(
    "ATELIER_ORIGINS",
    "http://127.0.0.1:8000,http://localhost:8000",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths that bypass auth even when it is enabled.
_PUBLIC_PREFIXES = ("/api/auth", "/share/")


@app.middleware("http")
async def timing_and_auth(request: Request, call_next):
    path = request.url.path

    if auth.enabled() and path.startswith("/api") and not path.startswith(_PUBLIC_PREFIXES):
        if not auth.valid_session(request.cookies.get(auth.COOKIE_NAME)):
            return JSONResponse({"error": "unauthorized"}, status_code=401)

    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    if path.startswith("/api") or path.startswith("/share/"):
        metrics.record_request(path, request.method, response.status_code, duration_ms)
    return response


for r in (
    auth_router.router, config_router.router, chat.router, memory.router, notes.router,
    tasks.router, files.router, research_router.router, skills.router, flashcards.router,
    cowriter_router.router, email_router.router, mcp_router.router, web.router,
    search_router.router, metrics_router.router,
):
    app.include_router(r)

# Static files (must be mounted last so it doesn't shadow the API routes).
app.mount("/", StaticFiles(directory="static", html=True), name="static")
