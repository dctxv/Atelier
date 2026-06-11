"""SQLite storage core (WAL) with a single serialized writer.

Design (Part 1.1):
  - WAL journal so many readers run while one writer writes.
  - ALL writes funnel through a one-thread executor, so there is effectively a
    single writer connection. That is what keeps concurrent PC + phone +
    background writes from ever hitting "database is locked".
  - Reads run on a small pool of connections (WAL readers don't block).
  - Every connection loads sqlite-vec and sets the WAL pragmas.

Routers never import sqlite3; they call the async helpers here (or a repo
module that wraps them). Nothing in this file imports FastAPI.
"""
from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import sqlite_vec

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "atelier.db"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# Standard embedding width across the app. Endpoint embeddings are projected to
# this width (Matryoshka-style truncate/pad) so the vec0 tables stay fixed.
EMBED_DIM = 256

# A single writer thread => writes are serialized => no lock contention.
_write_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="db-writer")
# Eight reader threads — retrieval now fans out to 5 concurrent reads (memory vec,
# memory FTS, doc vec, doc FTS, pinned); 8 gives headroom without contention on
# the write pool's connection.
_read_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="db-reader")

_local = threading.local()


def now() -> int:
    """Integer epoch seconds — the timestamp convention used everywhere."""
    return int(time.time())


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _conn() -> sqlite3.Connection:
    """One connection per worker thread, created lazily and reused."""
    c = getattr(_local, "conn", None)
    if c is None:
        c = _connect()
        _local.conn = c
    return c


# ── Low-level async wrappers ──────────────────────────────────────────────────

async def read(fn):
    """Run fn(conn) on a reader thread; return its result."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_read_pool, lambda: fn(_conn()))


async def write(fn):
    """Run fn(conn) on the single writer thread inside a transaction.

    Commits on success, rolls back on error. fn may issue many statements.
    """
    loop = asyncio.get_running_loop()

    def _op():
        conn = _conn()
        try:
            result = fn(conn)
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise

    return await loop.run_in_executor(_write_pool, _op)


# ── Convenience helpers ───────────────────────────────────────────────────────

async def execute(sql: str, params=()):
    def op(c):
        cur = c.execute(sql, params)
        return cur.lastrowid
    return await write(op)


async def executemany(sql: str, seq):
    def op(c):
        c.executemany(sql, seq)
    return await write(op)


async def fetchall(sql: str, params=()) -> list[dict]:
    def op(c):
        return [dict(r) for r in c.execute(sql, params).fetchall()]
    return await read(op)


async def fetchone(sql: str, params=()):
    def op(c):
        row = c.execute(sql, params).fetchone()
        return dict(row) if row else None
    return await read(op)


def serialize_f32(vec) -> bytes:
    """Pack a float list for a vec0 float[] column / MATCH query."""
    return sqlite_vec.serialize_float32(list(vec))


# ── Migrations ────────────────────────────────────────────────────────────────

async def bump_mutation_seq() -> int:
    """Increment the memory mutation sequence counter and return the new value."""
    def op(conn):
        row = conn.execute(
            "SELECT value FROM app_config WHERE key='memory_mutation_seq'"
        ).fetchone()
        seq = int(row["value"]) + 1 if row else 1
        conn.execute(
            "INSERT INTO app_config(key,value) VALUES('memory_mutation_seq',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(seq),),
        )
        return seq
    return await write(op)


async def init_db():
    """Apply the idempotent schema. Safe to run on every startup."""
    sql = SCHEMA_PATH.read_text(encoding="utf-8")

    def op(conn):
        conn.executescript(sql)
        # ALTER TABLE ADD COLUMN is idempotent-friendly in SQLite but executescript
        # does not suppress duplicate-column errors, so we run these migrations
        # separately inside try/except (no-op if column already exists).
        _migrations = [
            "ALTER TABLE document    ADD COLUMN project_id TEXT",
            "ALTER TABLE memory_atom ADD COLUMN project_id TEXT",
            "ALTER TABLE session     ADD COLUMN project_id TEXT",
            "ALTER TABLE project     ADD COLUMN description TEXT",
            # Weekly diff note columns (Fix 3 — never re-ingest digest as memory atoms)
            "ALTER TABLE note ADD COLUMN source_kind TEXT",
            "ALTER TABLE note ADD COLUMN meta        TEXT",
            # Living Memory System v2 — new columns on memory_atom (all nullable)
            "ALTER TABLE memory_atom ADD COLUMN subject           TEXT",
            "ALTER TABLE memory_atom ADD COLUMN predicate         TEXT",
            "ALTER TABLE memory_atom ADD COLUMN predicate_category TEXT",
            "ALTER TABLE memory_atom ADD COLUMN object            TEXT",
            "ALTER TABLE memory_atom ADD COLUMN polarity          REAL",
            "ALTER TABLE memory_atom ADD COLUMN intensity         REAL",
            "ALTER TABLE memory_atom ADD COLUMN modality          TEXT",
            "ALTER TABLE memory_atom ADD COLUMN confidence        REAL",
            "ALTER TABLE memory_atom ADD COLUMN valid_from        INTEGER",
            "ALTER TABLE memory_atom ADD COLUMN valid_until       INTEGER",
            "ALTER TABLE memory_atom ADD COLUMN temporal_raw      TEXT",
            "ALTER TABLE memory_atom ADD COLUMN status            TEXT DEFAULT 'active'",
            "ALTER TABLE memory_atom ADD COLUMN superseded_by     TEXT",
            "ALTER TABLE memory_atom ADD COLUMN meta              TEXT",
            # Task source tracking for assistant commitments
            "ALTER TABLE task ADD COLUMN source_kind TEXT",
            "ALTER TABLE task ADD COLUMN source_id   TEXT",
        ]
        for stmt in _migrations:
            try:
                conn.execute(stmt)
                conn.commit()
            except Exception:
                pass  # Column already exists — safe to ignore

        # Indexes that depend on the freshly-added columns.
        _post_indexes = [
            "CREATE INDEX IF NOT EXISTS idx_document_project ON document(project_id, status)",
            "CREATE INDEX IF NOT EXISTS idx_atom_project     ON memory_atom(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_session_project  ON session(project_id)",
            # Living Memory System v2 indexes
            "CREATE INDEX IF NOT EXISTS idx_atom_subj_pred ON memory_atom(subject, predicate, status)",
            "CREATE INDEX IF NOT EXISTS idx_atom_status    ON memory_atom(status, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_atom_modality  ON memory_atom(modality, status)",
            "CREATE INDEX IF NOT EXISTS idx_task_source    ON task(source_kind, source_id)",
        ]
        for stmt in _post_indexes:
            try:
                conn.execute(stmt)
                conn.commit()
            except Exception:
                pass

    await write(op)


def shutdown():
    _write_pool.shutdown(wait=True)
    _read_pool.shutdown(wait=False)
