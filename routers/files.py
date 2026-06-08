"""Files + share links (Part 2.6).

The public download route lives at /share/{token} (outside /api so it bypasses
auth) and streams only through the validating handler — raw paths are never
exposed. Expiry, download count, and a simple per-window rate limit are
enforced before the stream starts.
"""
from __future__ import annotations

import mimetypes
import re
import uuid

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from services import db, documents as doc_service, files
from workers import jobs

router = APIRouter()
api = APIRouter(prefix="/api")

RATE_LIMIT_PER_MIN = 30


# ── Files ─────────────────────────────────────────────────────────────────────

@api.get("/files")
async def get_files():
    return {"files": await files.list_files()}


_INGEST_MIMES = {
    "application/pdf", "text/plain", "text/markdown",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_INGEST_EXTS = {".pdf", ".txt", ".md", ".docx"}


@api.post("/files/upload")
async def upload_file(file: UploadFile = File(...)):
    files.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    file_id = str(uuid.uuid4())
    safe = re.sub(r"[^\w.\-]", "_", file.filename or "upload")
    stored_name = f"{file_id}_{safe}"
    content = await file.read()
    (files.UPLOADS_DIR / stored_name).write_bytes(content)
    mime = file.content_type or mimetypes.guess_type(safe)[0] or "application/octet-stream"
    entry = await files.create(file.filename or "upload", stored_name, len(content), mime)

    # Kick off document ingest for supported types (PDF, txt, md, docx).
    import os
    ext = os.path.splitext(safe)[1].lower()
    if mime in _INGEST_MIMES or ext in _INGEST_EXTS:
        doc = await doc_service.create(file.filename or safe, mime, len(content))
        await jobs.enqueue("ingest_document", {"doc_id": doc["id"], "file_id": entry["id"]})
        entry["document_id"] = doc["id"]

    return {"ok": True, "file": entry}


@api.delete("/files/{file_id}")
async def delete_file(file_id: str):
    target = await files.delete(file_id)
    if not target:
        raise HTTPException(404, "File not found")
    path = files.UPLOADS_DIR / target["stored_name"]
    if path.exists():
        path.unlink()
    return {"ok": True}


@api.get("/files/{file_id}/download")
async def download_file(file_id: str):
    target = await files.get(file_id)
    if not target:
        raise HTTPException(404, "File not found")
    path = files.UPLOADS_DIR / target["stored_name"]
    if not path.exists():
        raise HTTPException(404, "File data not found on disk")
    return FileResponse(str(path), filename=target["name"],
                        media_type=target.get("type", "application/octet-stream"))


# ── Shares ────────────────────────────────────────────────────────────────────

@api.get("/shares")
async def list_shares():
    return {"shares": await files.list_shares()}


@api.post("/files/{file_id}/share")
async def create_share(file_id: str, request: Request):
    data = await request.json()
    expires_at = data.get("expires_at")  # epoch seconds or None
    if data.get("expires_in_hours"):
        expires_at = db.now() + int(data["expires_in_hours"]) * 3600
    share = await files.create_share(file_id, expires_at, data.get("max_downloads"))
    if not share:
        raise HTTPException(404, "File not found")
    return {"ok": True, "share": share, "url": f"/share/{share['token']}"}


@api.delete("/shares/{share_id}")
async def revoke_share(share_id: str):
    if not await files.revoke_share(share_id):
        raise HTTPException(404, "Share not found")
    return {"ok": True}


@router.get("/share/{token}")
async def public_download(token: str, request: Request):
    share = await files.resolve_share(token)
    if not share:
        raise HTTPException(404, "Link not found")
    if share["expires_at"] and db.now() > share["expires_at"]:
        raise HTTPException(404, "Link expired")
    if share["max_downloads"] is not None and share["downloads"] >= share["max_downloads"]:
        raise HTTPException(404, "Download limit reached")

    ip = request.client.host if request.client else "?"
    if await files.recent_access_count(share["id"], 60) >= RATE_LIMIT_PER_MIN:
        raise HTTPException(429, "Rate limit exceeded")

    target = await files.get(share["file_id"])
    if not target:
        raise HTTPException(404, "File not found")
    path = files.UPLOADS_DIR / target["stored_name"]
    if not path.exists():
        raise HTTPException(404, "File data not found")

    await files.record_access_and_increment(share, ip)
    return FileResponse(str(path), filename=target["name"],
                        media_type=target.get("type", "application/octet-stream"))


router.include_router(api)
