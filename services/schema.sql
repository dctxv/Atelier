-- Atelier — v1 baseline schema.
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
    created_at INTEGER NOT NULL,
    meta       TEXT
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
-- Partial index for pinned-only lookup; keeps the hot-path pinned fetch sub-ms.
CREATE INDEX IF NOT EXISTS idx_atom_pinned  ON memory_atom(pinned, created_at) WHERE pinned=1;

-- Vectors live in a sqlite-vec vec0 table keyed by memory_atom.rowid.
-- v1 stores float32 @ 256 dims with cosine distance; int8 quantization is the
-- first scaling lever (deferred until the Part 4 test proves it's needed).
CREATE VIRTUAL TABLE IF NOT EXISTS memory_vec USING vec0(
    embedding float[256] distance_metric=cosine
);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(text);

-- Rebuildable emergent strand layer. These rows label geometry-derived
-- clusters; deleting this table must not delete or alter memory facts.
CREATE TABLE IF NOT EXISTS memory_strands (
    id              TEXT PRIMARY KEY,
    label           TEXT,
    label_embedding BLOB,
    centroid        BLOB,
    atom_count      INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'active', -- active | dormant | merged
    merged_into     TEXT,
    color           TEXT,
    glyph           TEXT,
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_strands_status ON memory_strands(status, atom_count);

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
    source_kind TEXT,
    source_id   TEXT,
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_task_source ON task(source_kind, source_id);

-- ── Commitments ──────────────────────────────────────────────────────────────
-- Proposed commitments are review-gated. Confirming one creates/links a task;
-- rejecting one leaves no task behind.
CREATE TABLE IF NOT EXISTS commitment (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    description  TEXT,
    status       TEXT DEFAULT 'proposed', -- proposed | active | rejected | done
    source_kind  TEXT DEFAULT 'chat',
    source_id    TEXT,                    -- e.g. session id
    atom_id      TEXT,                    -- extracted memory atom that triggered it
    task_id      TEXT,                    -- created only after confirmation
    context_json TEXT,                    -- JSON links/evidence
    created_at   INTEGER NOT NULL,
    updated_at   INTEGER NOT NULL,
    confirmed_at INTEGER,
    rejected_at  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_commitment_status ON commitment(status, created_at);
CREATE INDEX IF NOT EXISTS idx_commitment_atom   ON commitment(atom_id);
CREATE INDEX IF NOT EXISTS idx_commitment_task   ON commitment(task_id);

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

-- ── Web search layer ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS search_cache (
    id           TEXT PRIMARY KEY,
    query_norm   TEXT NOT NULL,
    params_hash  TEXT NOT NULL,         -- normalized query + params (recency/provider/depth)
    response_json TEXT NOT NULL,        -- the serialized SearchResponse
    fetched_at   INTEGER NOT NULL,
    ttl_seconds  INTEGER NOT NULL,      -- volatility-aware TTL
    hits         INTEGER DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_search_cache_key ON search_cache(params_hash);

CREATE TABLE IF NOT EXISTS search_provider_usage (
    provider TEXT NOT NULL,
    month    TEXT NOT NULL,             -- 'YYYY-MM'
    calls    INTEGER DEFAULT 0,
    errors   INTEGER DEFAULT 0,
    PRIMARY KEY (provider, month)
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

-- ── Documents + RAG ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS document (
    id          TEXT PRIMARY KEY,
    filename    TEXT NOT NULL,
    mime        TEXT,
    byte_size   INTEGER,
    doc_date    INTEGER,           -- best-effort original date; NULL if unknown
    status      TEXT NOT NULL,     -- queued | extracting | embedding | ready | failed
    error       TEXT,              -- reason when status = failed
    chunk_count INTEGER DEFAULT 0,
    abstract    TEXT,              -- cheap-model 2-sentence summary, filled after ready
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_document_status ON document(status, created_at);

CREATE TABLE IF NOT EXISTS document_chunk (
    id          TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    seq         INTEGER NOT NULL,  -- order within the document
    text        TEXT NOT NULL,
    char_start  INTEGER,           -- byte offsets in extracted text (for citation)
    char_end    INTEGER,
    created_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_docchunk_doc ON document_chunk(document_id);

CREATE VIRTUAL TABLE IF NOT EXISTS document_chunk_vec USING vec0(
    embedding float[256] distance_metric=cosine
);

CREATE VIRTUAL TABLE IF NOT EXISTS document_chunk_fts USING fts5(text);

-- ── Model registry (Part II Extension A) ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS model_registry (
    id             TEXT PRIMARY KEY,   -- e.g. "google/gemini-2.5-flash-lite"
    label          TEXT NOT NULL,
    input_price    REAL,               -- USD per 1M tokens
    output_price   REAL,               -- USD per 1M tokens
    cache_read     REAL,               -- USD per 1M cached tokens
    context_window INTEGER,
    tier_hint      TEXT DEFAULT 'standard',  -- cheap | standard | premium
    enabled        INTEGER DEFAULT 1
);

-- ── Usage telemetry (Part II Extension C) ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS usage_daily (
    day           TEXT NOT NULL,   -- YYYY-MM-DD
    model         TEXT NOT NULL,
    task          TEXT NOT NULL DEFAULT 'unknown',
    input_tokens  INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    est_cost_usd  REAL DEFAULT 0,
    PRIMARY KEY (day, model, task)
);

-- ── Deep Research v2 ─────────────────────────────────────────────────────────

-- Companion metadata for research jobs (stats, round count, duration).
-- Separate table so the schema stays additive — no ALTER on existing rows.
CREATE TABLE IF NOT EXISTS research_meta (
    research_id TEXT PRIMARY KEY,
    meta        TEXT           -- JSON: {"Duration":"42s","Rounds":2,"Claims":18}
);

-- Claim-level verification layer.
CREATE TABLE IF NOT EXISTS claim (
    id            TEXT PRIMARY KEY,
    research_id   TEXT NOT NULL,
    text          TEXT NOT NULL,
    section_idx   INTEGER,
    confidence    REAL,
    stance        TEXT,        -- supported | disputed | single_source | unverified
    created_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_claim_research ON claim(research_id);

CREATE TABLE IF NOT EXISTS claim_evidence (
    id           TEXT PRIMARY KEY,
    claim_id     TEXT NOT NULL,
    chunk_id     TEXT,
    url          TEXT,
    published_at INTEGER,
    entail       REAL,         -- entailment strength for this evidence→claim pair
    polarity     TEXT,         -- supports | refutes | neutral
    created_at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_claim ON claim_evidence(claim_id);

-- Entity graph extracted from verified claims.
CREATE TABLE IF NOT EXISTS entity (
    id          TEXT PRIMARY KEY,
    research_id TEXT,
    name        TEXT NOT NULL,
    kind        TEXT,          -- concept|metric|substance|condition|person|org
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS relation (
    id          TEXT PRIMARY KEY,
    research_id TEXT,
    src_entity  TEXT NOT NULL,
    dst_entity  TEXT NOT NULL,
    kind        TEXT,          -- affects|increases|decreases|correlates|contradicts
    claim_id    TEXT,
    created_at  INTEGER NOT NULL
);

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

-- ── Projects ─────────────────────────────────────────────────────────────────
-- NULL project_id = global (existing behavior unchanged).
-- ALTER TABLE ADD COLUMN is O(1) metadata-only in SQLite; safe on live DBs.

CREATE TABLE IF NOT EXISTS project (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    description  TEXT,               -- short blurb; only datum visible to global chat
    instructions TEXT,               -- project-scoped system prompt (Tier 0)
    icon         TEXT DEFAULT 'projects',
    created_at   INTEGER NOT NULL,
    updated_at   INTEGER NOT NULL
);

-- NOTE: the project_id columns are added by ALTER TABLE migrations in db.py,
-- and the indexes that depend on them are created there *after* the ALTERs run
-- (they cannot live here because executescript runs before the columns exist).

-- ── Living Memory System v2 ──────────────────────────────────────────────────

-- Append-only audit trail for material atom changes.
CREATE TABLE IF NOT EXISTS memory_event (
    id         TEXT PRIMARY KEY,
    atom_id    TEXT NOT NULL,
    kind       TEXT NOT NULL,
    detail     TEXT,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mevent_atom ON memory_event(atom_id);
CREATE INDEX IF NOT EXISTS idx_mevent_kind ON memory_event(kind, created_at);

-- Open questions/uncertainties surfaced for review.
CREATE TABLE IF NOT EXISTS memory_question (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    atom_ids    TEXT NOT NULL,
    prompt_text TEXT NOT NULL,
    status      TEXT DEFAULT 'open',
    created_at  INTEGER NOT NULL,
    resolved_at INTEGER,
    resolution  TEXT
);
CREATE INDEX IF NOT EXISTS idx_mquestion_status ON memory_question(status, created_at);
CREATE INDEX IF NOT EXISTS idx_mquestion_kind   ON memory_question(kind, created_at);

-- Slot-pattern table for predictive pre-fetch (Tier 3).
CREATE TABLE IF NOT EXISTS memory_pattern (
    slot       TEXT PRIMARY KEY,
    query_vec  BLOB,
    count      INTEGER DEFAULT 0,
    last_hit   INTEGER
);
