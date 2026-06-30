"""Document management API — list, status-poll, delete.

All mutation routes cascade correctly: deleting a document removes its chunks,
vectors, and FTS entries in one atomic transaction (services/documents.delete).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from services import documents
from workers import jobs

router = APIRouter(prefix="/api")


@router.get("/documents")
async def list_documents():
    return {"documents": await documents.list_all()}


@router.get("/documents/{doc_id}")
async def get_document(doc_id: str):
    doc = await documents.get(doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    deleted = await documents.delete(doc_id)
    if not deleted:
        raise HTTPException(404, "Document not found")
    return {"ok": True}


@router.post("/documents/{doc_id}/reindex")
async def reindex_document(doc_id: str):
    """Re-ingest an existing document with section-aware chunking.

    Drops existing chunks and re-runs the full extract→chunk→embed pipeline.
    The document's file_id must have been stored at upload time. Returns 202
    immediately; progress is tracked via GET /api/documents/{doc_id}.
    """
    doc = await documents.get(doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    if not doc.get("file_id"):
        raise HTTPException(400, "Document has no associated file_id — cannot reindex. "
                            "This document was uploaded before file_id tracking was added.")
    await jobs.enqueue("reindex_document", {"doc_id": doc_id})
    return {"ok": True, "status": "reindex queued"}


@router.get("/documents/usage/summary")
async def usage_summary():
    """Return per-model daily token usage for the last 30 days."""
    from services import db
    rows = await db.fetchall(
        "SELECT day, model, task, input_tokens, output_tokens, est_cost_usd "
        "FROM usage_daily ORDER BY day DESC, model LIMIT 500"
    )
    return {"usage": rows}
