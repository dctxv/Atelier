-- The Atelier — v1 baseline schema.
-- UUID text ids; integer-epoch (seconds) timestamps throughout.
-- This file is idempotent: every statement is IF NOT EXISTS so it doubles
-- as the migration runner on startup.

-- ── Config & endpoints ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS endpoint (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    base_url    TEXT NOT NULL,
    api_key_enc TEXT,                 -- encrypted at rest (services/crypto.py)
    type        TEXT DEFAULT 'local',
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS app_config (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- ── Chat ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS session (
    id         TEXT PRIMARY KEY,
    name       TEXT,
    model      TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS message (
    id         TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    model      TEXT,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_message_session ON message(session_id, created_at);

-- ── Memory (the hub) ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS memory_atom (
    id           TEXT PRIMARY KEY,
    text         TEXT NOT NULL,
    type         TEXT DEFAULT 'fact',
    salience     REAL DEFAULT 1.0,
    source_kind  TEXT DEFAULT 'manual',  -- chat | research | note | email | manual
    source_id    TEXT,
    created_at   INTEGER NOT NULL,
    last_used_at INTEGER,
    pinned       INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_atom_created ON memory_atom(created_at);
CREATE INDEX IF NOT EXISTS idx_atom_source  ON memory_atom(source_kind, source_id);

-- Vectors live in a sqlite-vec vec0 table keyed by memory_atom.rowid.
-- v1 stores float32 @ 256 dims with cosine distance; int8 quantization is the
-- first scaling lever (deferred until the Part 4 test proves it's needed).
CREATE VIRTUAL TABLE IF NOT EXISTS memory_vec USING vec0(
    embedding float[256] distance_metric=cosine
);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(text);

-- ── Research ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS research (
    id           TEXT PRIMARY KEY,
    query        TEXT NOT NULL,
    status       TEXT DEFAULT 'queued',
    title        TEXT,
    summary      TEXT,
    created_at   INTEGER NOT NULL,
    completed_at INTEGER,
    error        TEXT
);

CREATE TABLE IF NOT EXISTS research_section (
    id          TEXT PRIMARY KEY,
    research_id TEXT NOT NULL,
    idx         INTEGER NOT NULL,
    title       TEXT,
    content     TEXT
);
CREATE INDEX IF NOT EXISTS idx_section_research ON research_section(research_id, idx);

CREATE TABLE IF NOT EXISTS research_source (
    id          TEXT PRIMARY KEY,
    research_id TEXT NOT NULL,
    url         TEXT,
    title       TEXT
);
CREATE INDEX IF NOT EXISTS idx_source_research ON research_source(research_id);

CREATE TABLE IF NOT EXISTS research_chunk (
    id          TEXT PRIMARY KEY,
    research_id TEXT NOT NULL,
    url         TEXT,
    title       TEXT,
    text        TEXT,
    fetched_at  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_chunk_research ON research_chunk(research_id);

CREATE VIRTUAL TABLE IF NOT EXISTS research_chunk_vec USING vec0(
    embedding float[256] distance_metric=cosine
);

-- ── Notes ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS note (
    id         TEXT PRIMARY KEY,
    title      TEXT,
    body       TEXT,
    pinned     INTEGER DEFAULT 0,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

-- ── Tasks (pre-existing surface; kept on the shared core) ────────────────────
CREATE TABLE IF NOT EXISTS task (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    description TEXT,
    status      TEXT DEFAULT 'todo',
    priority    TEXT DEFAULT 'medium',
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL
);

-- ── Skills (pre-existing; drives chat system-prompt injection) ───────────────
CREATE TABLE IF NOT EXISTS skill (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    prompt      TEXT,
    category    TEXT DEFAULT 'general',
    icon        TEXT DEFAULT 'tasks',
    enabled     INTEGER DEFAULT 1,
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL
);

-- ── Flashcards ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS deck (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS card (
    id            TEXT PRIMARY KEY,
    deck_id       TEXT NOT NULL,
    front         TEXT NOT NULL,
    back          TEXT NOT NULL,
    source_kind   TEXT,
    source_id     TEXT,
    stability     REAL,
    difficulty    REAL,
    due_at        INTEGER,
    reps          INTEGER DEFAULT 0,
    lapses        INTEGER DEFAULT 0,
    last_review_at INTEGER,
    state         INTEGER DEFAULT 0,    -- FSRS card state enum
    step          INTEGER,              -- FSRS learning step
    fsrs_json     TEXT,                 -- full FSRS Card round-trip (source of truth)
    created_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_card_deck ON card(deck_id);
CREATE INDEX IF NOT EXISTS idx_card_due  ON card(due_at);

CREATE TABLE IF NOT EXISTS review_log (
    id             TEXT PRIMARY KEY,
    card_id        TEXT NOT NULL,
    rating         INTEGER NOT NULL,
    reviewed_at    INTEGER NOT NULL,
    elapsed_days   REAL,
    scheduled_days REAL
);
CREATE INDEX IF NOT EXISTS idx_review_card ON review_log(card_id);

-- ── Email ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mail_account (
    id         TEXT PRIMARY KEY,
    address    TEXT NOT NULL,
    protocol   TEXT DEFAULT 'imap',
    creds_enc  TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS mail_message (
    id              TEXT PRIMARY KEY,
    account_id      TEXT NOT NULL,
    uid             TEXT,
    from_addr       TEXT,
    subject         TEXT,
    snippet         TEXT,
    received_at     INTEGER,
    category        TEXT,
    category_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_mail_account ON mail_message(account_id, received_at);

CREATE TABLE IF NOT EXISTS mail_draft (
    id          TEXT PRIMARY KEY,
    in_reply_to TEXT,
    body        TEXT,
    created_at  INTEGER NOT NULL,
    sent_at     INTEGER
);

-- ── Files & shares ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS file (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    size        INTEGER,
    type        TEXT,
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS share (
    id            TEXT PRIMARY KEY,
    file_id       TEXT NOT NULL,
    token         TEXT UNIQUE NOT NULL,
    expires_at    INTEGER,
    max_downloads INTEGER,
    downloads     INTEGER DEFAULT 0,
    created_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_share_token ON share(token);

CREATE TABLE IF NOT EXISTS share_access (
    id          TEXT PRIMARY KEY,
    share_id    TEXT NOT NULL,
    ip          TEXT,
    accessed_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_share_access ON share_access(share_id, accessed_at);

-- ── Jobs & infrastructure ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL,
    status      TEXT DEFAULT 'queued',  -- queued | running | done | error
    payload     TEXT,
    attempts    INTEGER DEFAULT 0,
    last_error  TEXT,
    created_at  INTEGER NOT NULL,
    finished_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, created_at);

CREATE TABLE IF NOT EXISTS embedding_cache (
    content_hash TEXT PRIMARY KEY,
    embedding    BLOB NOT NULL,
    model        TEXT,
    created_at   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS request_timing (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    path        TEXT,
    method      TEXT,
    status      INTEGER,
    duration_ms REAL,
    at          INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reqtiming_path ON request_timing(path, at);

CREATE TABLE IF NOT EXISTS job_timing (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    type          TEXT,
    duration_ms   REAL,
    queue_wait_ms REAL,
    at            INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobtiming_type ON job_timing(type, at);

-- ── MCP (Phase 6) ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mcp_call_log (
    id         TEXT PRIMARY KEY,
    server     TEXT,
    tool       TEXT,
    args       TEXT,
    result     TEXT,
    approved   INTEGER DEFAULT 0,
    error      TEXT,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mcp_log ON mcp_call_log(created_at);
