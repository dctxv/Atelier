"""Document repository — stores metadata, chunks, and vectors for uploaded files.

Mirrors the shape of services/memory.py: one function per operation, all I/O
through db.read() / db.write() so the single-writer invariant is preserved.

Lifecycle:
  queued → extracting → embedding → ready
                                  → failed (with error message)

retrieve_chunks() is called from services/retrieval.py to include document
content in the same hybrid retrieval pass as memory atoms.
"""
from __future__ import annotations

import json
import uuid

from . import db


def _shape(row: dict) -> dict:
    return {
        "id":          row["id"],
        "filename":    row["filename"],
        "mime":        row.get("mime"),
        "byte_size":   row.get("byte_size"),
        "status":      row["status"],
        "error":       row.get("error"),
        "chunk_count": row.get("chunk_count", 0),
        "abstract":    row.get("abstract"),
        "file_id":     row.get("file_id"),
        "created_at":  row["created_at"],
        "updated_at":  row["updated_at"],
    }


async def create(filename: str, mime: str | None, byte_size: int,
                 project_id: str | None = None,
                 file_id: str | None = None) -> dict:
    doc_id = str(uuid.uuid4())
    now = db.now()
    await db.execute(
        "INSERT INTO document(id, filename, mime, byte_size, status, project_id, file_id, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (doc_id, filename, mime, byte_size, "queued", project_id, file_id, now, now),
    )
    return await get(doc_id)


async def get(doc_id: str) -> dict | None:
    row = await db.fetchone("SELECT * FROM document WHERE id=?", (doc_id,))
    return _shape(row) if row else None


async def list_all() -> list[dict]:
    rows = await db.fetchall("SELECT * FROM document ORDER BY created_at DESC")
    return [_shape(r) for r in rows]


async def set_status(
    doc_id: str,
    status: str,
    error: str | None = None,
    chunk_count: int | None = None,
    abstract: str | None = None,
) -> None:
    now = db.now()
    await db.execute(
        "UPDATE document SET status=?, error=?, chunk_count=COALESCE(?,chunk_count), "
        "abstract=COALESCE(?,abstract), updated_at=? WHERE id=?",
        (status, error, chunk_count, abstract, now, doc_id),
    )


async def delete(doc_id: str) -> dict | None:
    """Delete document and all its chunks + vectors atomically."""
    row = await db.fetchone("SELECT * FROM document WHERE id=?", (doc_id,))
    if not row:
        return None

    def op(conn):
        # Remove FTS entries keyed by chunk rowids
        chunk_rows = conn.execute(
            "SELECT rowid FROM document_chunk WHERE document_id=?", (doc_id,)
        ).fetchall()
        for cr in chunk_rows:
            conn.execute("DELETE FROM document_chunk_fts WHERE rowid=?", (cr[0],))
            conn.execute("DELETE FROM document_chunk_vec WHERE rowid=?", (cr[0],))
        conn.execute("DELETE FROM document_chunk WHERE document_id=?", (doc_id,))
        conn.execute("DELETE FROM document WHERE id=?", (doc_id,))

    await db.write(op)
    return _shape(row)


async def add_chunk(
    doc_id: str,
    seq: int,
    text: str,
    vec: list[float],
    char_start: int,
    char_end: int,
    *,
    heading: str | None = None,
    heading_path: list[str] | None = None,
    depth: int | None = None,
    section_id: str | None = None,
    page_no: int | None = None,
    fts_text: str | None = None,
) -> str:
    """Insert one chunk + its vector + FTS entry in a single transaction.

    heading_path is serialised as JSON. fts_text is the heading-prefixed text
    for the FTS index (heading terms become searchable); when None, raw text is
    used (legacy / unstructured path — identical to previous behaviour).
    """
    chunk_id = str(uuid.uuid4())
    now = db.now()
    hp_json = json.dumps(heading_path) if heading_path else None
    index_text = fts_text if fts_text is not None else text

    def op(conn):
        conn.execute(
            "INSERT INTO document_chunk"
            "(id, document_id, seq, text, char_start, char_end,"
            " heading, heading_path, depth, section_id, page_no, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (chunk_id, doc_id, seq, text, char_start, char_end,
             heading, hp_json, depth, section_id, page_no, now),
        )
        rid = conn.execute(
            "SELECT rowid FROM document_chunk WHERE id=?", (chunk_id,)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO document_chunk_vec(rowid, embedding) VALUES(?,?)",
            (rid, db.serialize_f32(vec)),
        )
        conn.execute(
            "INSERT INTO document_chunk_fts(rowid, text) VALUES(?,?)",
            (rid, index_text),
        )

    await db.write(op)
    return chunk_id


async def delete_chunks(doc_id: str) -> int:
    """Delete all chunks for a document without removing the document row itself.

    Used by the reindex job so the document record (and its file_id) survives.
    Returns the number of chunks removed.
    """
    chunk_rows = await db.fetchall(
        "SELECT rowid FROM document_chunk WHERE document_id=?", (doc_id,)
    )
    if not chunk_rows:
        return 0

    def op(conn):
        for cr in chunk_rows:
            conn.execute("DELETE FROM document_chunk_fts WHERE rowid=?", (cr["rowid"],))
            conn.execute("DELETE FROM document_chunk_vec WHERE rowid=?", (cr["rowid"],))
        conn.execute("DELETE FROM document_chunk WHERE document_id=?", (doc_id,))

    await db.write(op)
    return len(chunk_rows)


async def sweep_orphans() -> int:
    """Remove chunks whose parent document no longer exists. Returns count removed."""
    orphans = await db.fetchall(
        "SELECT dc.id, dc.rowid FROM document_chunk dc "
        "LEFT JOIN document d ON d.id = dc.document_id WHERE d.id IS NULL"
    )
    if not orphans:
        return 0

    def op(conn):
        for o in orphans:
            conn.execute("DELETE FROM document_chunk_fts WHERE rowid=?", (o["rowid"],))
            conn.execute("DELETE FROM document_chunk_vec WHERE rowid=?", (o["rowid"],))
            conn.execute("DELETE FROM document_chunk WHERE id=?", (o["id"],))

    await db.write(op)
    return len(orphans)
