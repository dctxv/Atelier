"""Projects REST API.

  GET    /api/projects               list all projects
  POST   /api/projects               create project
  GET    /api/projects/{id}          get project detail + file count
  PATCH  /api/projects/{id}          update name / instructions
  DELETE /api/projects/{id}          delete project (disassociates files)
  GET    /api/projects/{id}/documents list project documents
  POST   /api/projects/{id}/documents/upload  upload file into project
  DELETE /api/projects/{id}/documents/{doc_id}  remove doc from project
  PATCH  /api/projects/{id}/documents/{doc_id}/assign  assign existing doc
  POST   /api/projects/{id}/manifest  build + return manifest text (for debugging)
  GET    /api/projects/{id}/memory    list project memory atoms
  PATCH  /api/memory/{atom_id}/promote  promote project atom → global
"""
from __future__ import annotations

import mimetypes
import re
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from services import db, documents, files as files_service, projects
from workers import jobs

router = APIRouter(prefix="/api")


# ── Schemas ───────────────────────────────────────────────────────────────────

class CreateProject(BaseModel):
    name: str
    instructions: str | None = None
    description: str | None = None


class PatchProject(BaseModel):
    name: str | None = None
    instructions: str | None = None
    description: str | None = None


# ── Project CRUD ──────────────────────────────────────────────────────────────

@router.get("/projects")
async def list_projects():
    return {"projects": await projects.list_all()}


@router.post("/projects")
async def create_project(body: CreateProject):
    p = await projects.create(body.name, body.instructions, body.description)
    return {"project": p}


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    p = await projects.get(project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    docs = await projects.list_documents(project_id)
    return {"project": p, "documents": docs}


@router.patch("/projects/{project_id}")
async def update_project(project_id: str, body: PatchProject):
    p = await projects.update(project_id, name=body.name,
                              instructions=body.instructions,
                              description=body.description)
    if not p:
        raise HTTPException(404, "Project not found")
    return {"project": p}


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    ok = await projects.delete(project_id)
    if not ok:
        raise HTTPException(404, "Project not found")
    return {"ok": True}


# ── Project documents ─────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/documents")
async def list_project_documents(project_id: str):
    p = await projects.get(project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    docs = await projects.list_documents(project_id)
    return {"documents": docs}


@router.post("/projects/{project_id}/documents/upload")
async def upload_project_document(project_id: str, file: UploadFile = File(...)):
    """Upload a file directly into a project."""
    p = await projects.get(project_id)
    if not p:
        raise HTTPException(404, "Project not found")

    allowed_exts = {"pdf", "txt", "md", "docx"}
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in allowed_exts:
        raise HTTPException(400, f"File type .{ext} not supported. Use: {', '.join(allowed_exts)}")

    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 25 MB)")

    # Persist bytes + file row using the same path as /api/files/upload, so the
    # ingest worker can load the source by file_id (it reads payload["file_id"]).
    files_service.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    file_uuid = str(uuid.uuid4())
    safe = re.sub(r"[^\w.\-]", "_", file.filename or "upload")
    stored_name = f"{file_uuid}_{safe}"
    (files_service.UPLOADS_DIR / stored_name).write_bytes(content)
    mime = file.content_type or mimetypes.guess_type(safe)[0] or "application/octet-stream"
    file_row = await files_service.create(file.filename or "upload", stored_name, len(content), mime)

    # Document record scoped to this project.
    doc = await documents.create(file.filename or safe, mime, len(content), project_id=project_id)

    # Enqueue ingestion (queued → extracting → embedding → ready).
    await jobs.enqueue("ingest_document", {"doc_id": doc["id"], "file_id": file_row["id"]})

    return {"document": doc}


@router.delete("/projects/{project_id}/documents/{doc_id}")
async def remove_project_document(project_id: str, doc_id: str):
    """Delete a document from a project."""
    doc = await documents.get(doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    deleted = await documents.delete(doc_id)
    if not deleted:
        raise HTTPException(500, "Delete failed")
    return {"ok": True}


@router.post("/projects/{project_id}/documents/{doc_id}/assign")
async def assign_document_to_project(project_id: str, doc_id: str):
    """Assign an existing (global) document to this project."""
    p = await projects.get(project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    ok = await projects.assign_document(doc_id, project_id)
    if not ok:
        raise HTTPException(404, "Document not found")
    return {"ok": True}


# ── Manifest (debug/inspection) ───────────────────────────────────────────────

@router.post("/projects/{project_id}/manifest")
async def get_manifest(project_id: str):
    """Build and return the project manifest for debugging."""
    p = await projects.get(project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    manifest_text, docs = await projects.build_manifest(project_id)
    return {
        "manifest": manifest_text,
        "file_count": len(docs),
        "estimated_tokens": max(1, len(manifest_text) // 4),
    }


# ── Project memory ────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/memory")
async def list_project_memory(project_id: str):
    p = await projects.get(project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    atoms = await db.fetchall(
        "SELECT * FROM memory_atom WHERE project_id=? ORDER BY created_at DESC LIMIT 200",
        (project_id,),
    )
    return {"atoms": [dict(a) for a in atoms]}


@router.patch("/memory/{atom_id}/promote")
async def promote_atom_to_global(atom_id: str):
    """Promote a project-scoped memory atom to global (project_id → NULL)."""
    atom = await db.fetchone("SELECT * FROM memory_atom WHERE id=?", (atom_id,))
    if not atom:
        raise HTTPException(404, "Memory atom not found")
    await db.execute(
        "UPDATE memory_atom SET project_id=NULL WHERE id=?", (atom_id,)
    )
    return {"ok": True, "atom_id": atom_id}
