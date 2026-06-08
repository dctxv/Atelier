"""Document ingest pipeline — background job registered as "ingest_document".

Flow (all off the hot path, run by the job queue):
  1. Extract text from the file (PDF / txt / md / docx)
  2. Chunk with fixed-size windows + overlap (mirrors research_chunk pattern)
  3. Embed each chunk via the shared local embedder
  4. Store chunks + vectors + FTS entries via documents.add_chunk()
  5. Generate a 2-sentence abstract with the cheap model
  6. Mark the document ready (or failed with a clear reason)

Scanned/image PDFs produce no extractable text and are marked failed rather than
ingesting garbage. OCR is deferred to v2.
"""
from __future__ import annotations

import io
from pathlib import Path

from services import documents, embeddings, files as files_service, llm
from . import jobs

CHUNK_CHARS = 1000   # mirrors CHUNK_CHARS in workers/research.py
CHUNK_OVERLAP = 150  # overlap to avoid mid-sentence cuts
MAX_FILE_MB = 25


def _chunk_text(text: str) -> list[tuple[str, int, int]]:
    """Return list of (chunk_text, char_start, char_end) with overlap."""
    chunks = []
    start = 0
    length = len(text)
    step = CHUNK_CHARS - CHUNK_OVERLAP
    while start < length:
        end = min(start + CHUNK_CHARS, length)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append((chunk, start, end))
        if end >= length:
            break
        start += step
    return chunks


def _extract_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages:
            t = page.extract_text() or ""
            if t.strip():
                pages.append(t)
        return "\n".join(pages)
    except Exception as e:
        raise RuntimeError(f"PDF extraction failed: {e}") from e


def _extract_docx(data: bytes) -> str:
    try:
        from docx import Document
        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        raise RuntimeError(f"DOCX extraction failed: {e}") from e


def _extract_text(data: bytes, mime: str | None, filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf" or (mime and "pdf" in mime):
        text = _extract_pdf(data)
        if not text.strip():
            raise RuntimeError(
                "No text found in this PDF. It may be a scanned image — "
                "OCR support is coming in a future version."
            )
        return text
    if ext in (".docx",) or (mime and "wordprocessingml" in mime):
        return _extract_docx(data)
    # Plain text, markdown, or anything else we treat as UTF-8 text
    try:
        return data.decode("utf-8", errors="replace")
    except Exception as e:
        raise RuntimeError(f"Could not decode file as text: {e}") from e


@jobs.register("ingest_document")
async def ingest_document(payload: dict):
    doc_id = payload["doc_id"]
    doc = await documents.get(doc_id)
    if not doc:
        return

    # Resolve the stored file path via the files service
    file_row = await files_service.get(payload["file_id"])
    if not file_row:
        await documents.set_status(doc_id, "failed", error="Source file record not found")
        return

    file_path = files_service.UPLOADS_DIR / file_row["stored_name"]
    if not file_path.exists():
        await documents.set_status(doc_id, "failed", error="Source file not found on disk")
        return

    if file_row.get("size", 0) > MAX_FILE_MB * 1024 * 1024:
        await documents.set_status(
            doc_id, "failed",
            error=f"File exceeds the {MAX_FILE_MB} MB limit for document ingestion",
        )
        return

    # ── Stage 1: Extract ─────────────────────────────────────────────────────
    await documents.set_status(doc_id, "extracting")
    try:
        data = file_path.read_bytes()
        text = _extract_text(data, doc.get("mime"), doc["filename"])
    except RuntimeError as e:
        await documents.set_status(doc_id, "failed", error=str(e))
        return

    if not text.strip():
        await documents.set_status(doc_id, "failed", error="No readable text found in document")
        return

    # ── Stage 2 + 3: Chunk + Embed ────────────────────────────────────────────
    await documents.set_status(doc_id, "embedding")
    chunks = _chunk_text(text)
    try:
        for seq, (chunk_text, char_start, char_end) in enumerate(chunks):
            vec = await embeddings.embed(chunk_text)
            await documents.add_chunk(doc_id, seq, chunk_text, vec, char_start, char_end)
    except Exception as e:
        await documents.set_status(doc_id, "failed", error=f"Embedding failed: {e}")
        return

    # ── Stage 4: Generate abstract (cheap model, best-effort) ─────────────────
    abstract = None
    try:
        preview = text[:2000]
        raw = await llm.cheap(
            [{"role": "system", "content":
              "Write exactly 2 sentences summarising the main topic of this document. "
              "Be concise and specific. Return only those 2 sentences, nothing else."},
             {"role": "user", "content": preview}],
            temperature=0.2, max_tokens=120, task="document_abstract",
        )
        abstract = raw.strip()
    except Exception:
        pass  # abstract is best-effort; never fail ingest because of it

    # ── Stage 5: Mark ready ───────────────────────────────────────────────────
    await documents.set_status(
        doc_id, "ready",
        chunk_count=len(chunks),
        abstract=abstract,
    )
