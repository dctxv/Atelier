"""Document management API — list, status-poll, delete.

All mutation routes cascade correctly: deleting a document removes its chunks,
vectors, and FTS entries in one atomic transaction (services/documents.delete).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from services import documents

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


@router.get("/documents/usage/summary")
async def usage_summary():
    """Return per-model daily token usage for the last 30 days."""
    from services import db
    rows = await db.fetchall(
        "SELECT day, model, task, input_tokens, output_tokens, est_cost_usd "
        "FROM usage_daily ORDER BY day DESC, model LIMIT 500"
    )
    return {"usage": rows}
