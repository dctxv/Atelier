"""Document ingest pipeline — background jobs "ingest_document" and "reindex_document".

Flow (all off the hot path, run by the job queue):
  1. Extract text from the file (PDF / txt / md / docx) → list[Block]
  2. Chunk with section-aware sliding window → list[Chunk]  (never crosses headings)
  3. Embed each chunk (heading_path prefix folded in when doc.heading_in_embedding=true)
  4. Store chunks + vectors + FTS entries via documents.add_chunk()
  5. Generate a 2-sentence abstract with the cheap model
  6. Mark the document ready (or failed with a clear reason)

Scanned/image PDFs produce no extractable text and are marked failed rather than
ingesting garbage. OCR is deferred to v2.

Section-aware chunking adds three capabilities:
  - heading_path breadcrumb on every chunk (never crosses a section boundary)
  - Heading text folded into the FTS index so section names are searchable
  - section_id groups chunks for neighbour expansion at retrieval time
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from services import db, documents, embeddings, files as files_service, llm
from . import jobs

CHUNK_CHARS = 1000   # mirrors CHUNK_CHARS in workers/research.py
CHUNK_OVERLAP = 150  # overlap to avoid mid-sentence cuts
MAX_FILE_MB = 25
HEADING_MAX_CHARS_PDF = 80   # [VALIDATE] heuristic heading length cap for PDF


# ── Typed intermediate structures ─────────────────────────────────────────────

@dataclass
class Block:
    """One logical paragraph / block with its section context."""
    text: str
    heading_path: list[str] = field(default_factory=list)  # [] = preamble / no structure
    depth: int | None = None    # heading level of the leaf (None = preamble)
    page_no: int | None = None  # 1-based page number, PDF only


@dataclass
class Chunk:
    """One storable chunk with full section metadata."""
    text: str
    char_start: int
    char_end: int
    heading: str | None         # leaf heading text
    heading_path: list[str]     # breadcrumb root→leaf ([] = unstructured)
    depth: int | None           # heading level of leaf
    section_id_ordinal: int     # 0-based; combined with doc_id at write time
    page_no: int | None


# ── Config helper ──────────────────────────────────────────────────────────────

async def _cfg(key: str, default):
    """Read a typed config value from app_config; fall back to default if absent."""
    row = await db.fetchone("SELECT value FROM app_config WHERE key=?", (key,))
    if row is None or row.get("value") is None:
        return default
    val = row["value"]
    if isinstance(default, bool):
        return val.lower() in ("1", "true", "yes")
    if isinstance(default, int):
        try:
            return int(val)
        except (ValueError, TypeError):
            return default
    return val


# ── Per-format block extractors (pure functions — no DB access) ───────────────

def _blocks_from_markdown(text: str) -> list[Block]:
    """Parse markdown / plaintext into Blocks with ATX + setext heading detection.

    # ATX headings (level from hash count) and setext underlines (=== / ---)
    are recognised. Content inside fenced code blocks is never treated as a
    heading. Blank lines flush the current paragraph so section seams are clean.
    """
    blocks: list[Block] = []
    heading_stack: list[tuple[int, str]] = []   # (level, heading_text)
    in_fence = False
    current_lines: list[str] = []
    lines = text.splitlines()
    skip_next = False

    def flush() -> None:
        nonlocal current_lines
        combined = "\n".join(current_lines).strip()
        if combined:
            path = [h for _, h in heading_stack]
            depth = heading_stack[-1][0] if heading_stack else None
            blocks.append(Block(text=combined, heading_path=path[:], depth=depth))
        current_lines = []

    for i, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue

        # Fenced code block tracking (``` or ~~~)
        if re.match(r'^(`{3,}|~{3,})', line):
            in_fence = not in_fence
            current_lines.append(line)
            continue

        if in_fence:
            current_lines.append(line)
            continue

        # ATX heading: # / ## / … / ######
        atx = re.match(r'^(#{1,6})\s+(.*)', line)
        if atx:
            flush()
            level = len(atx.group(1))
            heading_text = atx.group(2).strip()
            heading_stack = [(l, t) for l, t in heading_stack if l < level]
            heading_stack.append((level, heading_text))
            continue

        # Setext headings: lookahead one line
        if i + 1 < len(lines) and line.strip():
            next_line = lines[i + 1]
            if re.match(r'^={3,}\s*$', next_line):
                flush()
                heading_stack = [(l, t) for l, t in heading_stack if l < 1]
                heading_stack.append((1, line.strip()))
                skip_next = True
                continue
            # Avoid treating markdown list items (- item) as setext headings
            if (re.match(r'^-{3,}\s*$', next_line)
                    and not re.match(r'^\s*[-*+]\s', line)):
                flush()
                heading_stack = [(l, t) for l, t in heading_stack if l < 2]
                heading_stack.append((2, line.strip()))
                skip_next = True
                continue

        if not line.strip():
            flush()
        else:
            current_lines.append(line)

    flush()
    return blocks


def _blocks_from_docx(data: bytes) -> list[Block]:
    """Parse DOCX paragraphs using Word heading styles (Heading 1 … Heading 9).

    python-docx paragraph styles carry the heading level directly; this is the
    most reliable heading signal of any supported format.
    """
    from docx import Document  # noqa: PLC0415
    doc = Document(io.BytesIO(data))
    blocks: list[Block] = []
    heading_stack: list[tuple[int, str]] = []
    current_texts: list[str] = []

    def flush() -> None:
        nonlocal current_texts
        combined = "\n".join(current_texts).strip()
        if combined:
            path = [h for _, h in heading_stack]
            depth = heading_stack[-1][0] if heading_stack else None
            blocks.append(Block(text=combined, heading_path=path[:], depth=depth))
        current_texts = []

    for para in doc.paragraphs:
        style_name = (para.style.name or "") if para.style else ""
        text = para.text.strip()
        if not text:
            continue

        heading_match = re.match(r'^Heading\s+(\d+)$', style_name, re.IGNORECASE)
        is_title = style_name.lower() == "title"

        if is_title:
            flush()
            heading_stack = []
            heading_stack.append((1, text))
        elif heading_match:
            flush()
            level = int(heading_match.group(1))
            heading_stack = [(l, t) for l, t in heading_stack if l < level]
            heading_stack.append((level, text))
        else:
            current_texts.append(text)

    flush()
    return blocks


def _blocks_from_pdf(data: bytes) -> list[Block]:
    """Parse PDF pages into Blocks with best-effort numbered-heading detection.

    Numbered headings (1, 2.1, 3.1.2) are the most reliable signal and are
    preferred. A conservative word-count / capitalisation heuristic is also
    applied. If zero headings are detected in the whole document, all Blocks are
    emitted with heading_path=[] — identical to the previous flat behaviour.
    Raises RuntimeError (preserving the existing scanned-PDF message) when pypdf
    cannot extract any text.
    """
    try:
        from pypdf import PdfReader  # noqa: PLC0415
    except ImportError as e:
        raise RuntimeError(f"pypdf not available: {e}") from e

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as e:
        raise RuntimeError(f"PDF extraction failed: {e}") from e

    # Collect all lines with their page numbers
    all_lines: list[tuple[str, int]] = []
    for page_num, page in enumerate(reader.pages, 1):
        page_text = page.extract_text() or ""
        for line in page_text.splitlines():
            all_lines.append((line, page_num))

    if not any(line.strip() for line, _ in all_lines):
        # pypdf returned nothing — treat as scanned PDF (caller raises the message)
        return []

    NUMBERED = re.compile(r'^(\d+(?:\.\d+)*)\s+[A-Z\w]')

    def _is_heading(stripped: str) -> tuple[bool, int]:
        """Return (is_heading, level). Level from numbering depth or heuristic."""
        numbered = NUMBERED.match(stripped)
        if numbered and len(stripped) <= HEADING_MAX_CHARS_PDF:
            dotted = re.match(r'^([\d.]+)', stripped)
            level = dotted.group(1).count('.') + 1 if dotted else 1
            return True, level
        # Conservative heuristic: ≤ 8 words, no sentence-ending punctuation,
        # starts with capital, short enough to be a heading.  [VALIDATE]
        if (len(stripped) <= HEADING_MAX_CHARS_PDF
                and not re.search(r'[.!?;]$', stripped)
                and len(stripped.split()) <= 8
                and stripped and stripped[0].isupper()
                and not re.match(r'^\d', stripped)):  # numbered handled above
            return True, 2
        return False, 0

    # First pass: check whether this PDF has any detectable headings at all
    has_headings = any(
        _is_heading(line.strip())[0]
        for line, _ in all_lines if line.strip()
    )

    blocks: list[Block] = []
    heading_stack: list[tuple[int, str]] = []
    current_texts: list[str] = []
    current_page: int | None = None

    def flush(page_no: int | None = None) -> None:
        nonlocal current_texts
        combined = "\n".join(current_texts).strip()
        if combined:
            if has_headings:
                path = [h for _, h in heading_stack]
                depth = heading_stack[-1][0] if heading_stack else None
            else:
                path, depth = [], None
            blocks.append(Block(text=combined, heading_path=path[:],
                                depth=depth, page_no=page_no))
        current_texts = []

    for line, pno in all_lines:
        stripped = line.strip()
        if not stripped:
            flush(current_page)
            current_page = pno
            continue
        if current_page is None:
            current_page = pno

        if has_headings:
            is_h, level = _is_heading(stripped)
            if is_h:
                flush(current_page)
                heading_stack = [(l, t) for l, t in heading_stack if l < level]
                heading_stack.append((level, stripped))
                current_page = pno
                continue

        current_texts.append(stripped)

    flush(current_page)
    return blocks


def _extract_text(data: bytes, mime: str | None, filename: str) -> list[Block]:
    """Dispatch to the right per-format block extractor.

    Raises RuntimeError (with a user-visible message) on scanned PDFs and
    decode failures — matches the existing contract so ingest_document's
    try/except path is unchanged.
    """
    ext = Path(filename).suffix.lower()
    if ext == ".pdf" or (mime and "pdf" in mime):
        blocks = _blocks_from_pdf(data)
        if not any(b.text.strip() for b in blocks):
            raise RuntimeError(
                "No text found in this PDF. It may be a scanned image — "
                "OCR support is coming in a future version."
            )
        return blocks
    if ext == ".docx" or (mime and "wordprocessingml" in mime):
        try:
            return _blocks_from_docx(data)
        except Exception as e:
            raise RuntimeError(f"DOCX extraction failed: {e}") from e
    # Plain text, markdown, or anything else: decode as UTF-8
    try:
        text = data.decode("utf-8", errors="replace")
        return _blocks_from_markdown(text)
    except Exception as e:
        raise RuntimeError(f"Could not decode file as text: {e}") from e


# ── Section-aware chunker ──────────────────────────────────────────────────────

def _chunk_blocks(
    blocks: list[Block],
    chunk_chars: int = CHUNK_CHARS,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[Chunk]:
    """Produce Chunks from structured Blocks, never crossing a section boundary.

    Consecutive Blocks sharing the same heading_path form one section.  Within
    each section the existing sliding-window chunker (CHUNK_CHARS / CHUNK_OVERLAP)
    is applied.  char_start / char_end are global offsets into the canonical full
    text (blocks joined with "\\n\\n"), so they are monotonically increasing and
    round-trip back to the right substring.
    """
    if not blocks:
        return []

    # Build global character offsets for every block.
    # Full text = "\n\n".join(b.text for b in blocks)
    block_global_starts: list[int] = []
    offset = 0
    for i, block in enumerate(blocks):
        block_global_starts.append(offset)
        offset += len(block.text)
        if i < len(blocks) - 1:
            offset += 2  # "\n\n" separator

    chunks: list[Chunk] = []
    section_ordinal = -1
    step = max(1, chunk_chars - chunk_overlap)

    i = 0
    while i < len(blocks):
        section_ordinal += 1
        path = blocks[i].heading_path

        # Find the end of this section (first block with a different heading_path)
        j = i + 1
        while j < len(blocks) and blocks[j].heading_path == path:
            j += 1

        # Build section text and track its global start position
        section_blocks = blocks[i:j]
        section_global_start = block_global_starts[i]
        section_parts: list[str] = []
        for k, blk in enumerate(section_blocks):
            section_parts.append(blk.text)
            if k < len(section_blocks) - 1:
                section_parts.append("\n\n")
        section_text = "".join(section_parts)

        heading_path = path[:]
        heading = path[-1] if path else None
        depth = section_blocks[0].depth
        page_no = section_blocks[0].page_no

        # Sliding window within this section
        pos = 0
        length = len(section_text)
        while pos < length:
            end = min(pos + chunk_chars, length)
            chunk_text = section_text[pos:end].strip()
            if chunk_text:
                chunks.append(Chunk(
                    text=chunk_text,
                    char_start=section_global_start + pos,
                    char_end=section_global_start + end,
                    heading=heading,
                    heading_path=heading_path,
                    depth=depth,
                    section_id_ordinal=section_ordinal,
                    page_no=page_no,
                ))
            if end >= length:
                break
            pos += step

        i = j

    return chunks


# ── Ingest job ─────────────────────────────────────────────────────────────────

async def _run_ingest(doc_id: str, file_id: str) -> None:
    """Core ingest logic, shared by ingest_document and reindex_document."""
    doc = await documents.get(doc_id)
    if not doc:
        return

    file_row = await files_service.get(file_id)
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

    # Config knobs (all readable from app_config without a deploy)
    section_aware    = await _cfg("doc.section_aware",       True)
    heading_in_embed = await _cfg("doc.heading_in_embedding", True)
    heading_in_fts   = await _cfg("doc.heading_in_fts",      True)
    chunk_chars      = await _cfg("doc.chunk_chars",          CHUNK_CHARS)
    chunk_overlap    = await _cfg("doc.chunk_overlap",        CHUNK_OVERLAP)

    # Stage 1: Extract
    await documents.set_status(doc_id, "extracting")
    try:
        data = file_path.read_bytes()
        blocks = _extract_text(data, doc.get("mime"), doc["filename"])
    except RuntimeError as e:
        await documents.set_status(doc_id, "failed", error=str(e))
        return

    if not blocks or not any(b.text.strip() for b in blocks):
        await documents.set_status(doc_id, "failed", error="No readable text found in document")
        return

    # Stage 2+3: Chunk + Embed
    await documents.set_status(doc_id, "embedding")

    if section_aware:
        chunks = _chunk_blocks(blocks, chunk_chars, chunk_overlap)
    else:
        # Flat fallback: join all block text, apply legacy window chunker
        flat_text = "\n\n".join(b.text for b in blocks if b.text.strip())
        step = max(1, chunk_chars - chunk_overlap)
        flat_chunks_raw: list[Chunk] = []
        start = 0
        length = len(flat_text)
        ordinal = 0
        while start < length:
            end = min(start + chunk_chars, length)
            ct = flat_text[start:end].strip()
            if ct:
                flat_chunks_raw.append(Chunk(
                    text=ct, char_start=start, char_end=end,
                    heading=None, heading_path=[], depth=None,
                    section_id_ordinal=ordinal, page_no=None,
                ))
                ordinal += 1
            if end >= length:
                break
            start += step
        chunks = flat_chunks_raw

    try:
        for seq, c in enumerate(chunks):
            # Embedding input: heading_path prefix gives the model section context
            # without a per-chunk LLM call (free, deterministic).
            if c.heading_path and heading_in_embed:
                embed_input = " › ".join(c.heading_path) + "\n\n" + c.text
            else:
                embed_input = c.text

            vec = await embeddings.embed(embed_input)

            # FTS input: heading terms become searchable so "limitations section"
            # finds the right chunk even when the body text doesn't repeat the title.
            if c.heading_path and heading_in_fts:
                fts_text = " › ".join(c.heading_path) + "\n" + c.text
            else:
                fts_text = None  # add_chunk falls back to raw text

            await documents.add_chunk(
                doc_id, seq, c.text, vec, c.char_start, c.char_end,
                heading=c.heading,
                heading_path=c.heading_path if c.heading_path else None,
                depth=c.depth,
                # NULL section_id for unstructured chunks → legacy flat behaviour
                section_id=f"{doc_id}:{c.section_id_ordinal}" if c.heading_path else None,
                page_no=c.page_no,
                fts_text=fts_text,
            )
    except Exception as e:
        await documents.set_status(doc_id, "failed", error=f"Embedding failed: {e}")
        return

    # Stage 4: Generate abstract (cheap model, best-effort)
    abstract = None
    try:
        preview = "\n\n".join(b.text for b in blocks[:10])[:2000]
        raw = await llm.cheap(
            [{"role": "system", "content":
              "Write exactly 2 sentences summarising the main topic of this document. "
              "Be concise and specific. Return only those 2 sentences, nothing else."},
             {"role": "user", "content": preview}],
            temperature=0.2, max_tokens=120, task="document_abstract",
        )
        abstract = raw.strip()
    except Exception:
        pass

    await documents.set_status(
        doc_id, "ready",
        chunk_count=len(chunks),
        abstract=abstract,
    )


@jobs.register("ingest_document")
async def ingest_document(payload: dict):
    doc_id = payload["doc_id"]
    file_id = payload["file_id"]
    await _run_ingest(doc_id, file_id)


@jobs.register("reindex_document")
async def reindex_document(payload: dict):
    """Re-ingest an existing document with section-aware chunking.

    Deletes existing chunks (FTS + vec + rows) but leaves the document record
    intact so file_id and metadata survive. Then runs the full ingest pipeline.
    The original file must still be on disk (it is never removed by document delete).
    """
    doc_id = payload["doc_id"]
    doc = await documents.get(doc_id)
    if not doc:
        return

    file_id = doc.get("file_id") or payload.get("file_id")
    if not file_id:
        await documents.set_status(doc_id, "failed",
                                   error="No file_id on document record — cannot reindex")
        return

    # Drop existing chunks and reset status
    await documents.delete_chunks(doc_id)
    await documents.set_status(doc_id, "queued")

    await _run_ingest(doc_id, file_id)
