"""Fixture test for section-aware document retrieval.

Follows the repo convention (see scripts/test_clustering.py):
  - db.configure_for_tests(tmp_path) before any DB use
  - db.init_db() to apply schema + migrations
  - db.shutdown() in a finally block
  - Pure-function tests need no DB at all

Run with:
  python -m scripts.test_section_retrieval
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

# ── Pure-function tests (no DB, no server) ────────────────────────────────────

def _import_worker():
    from workers.documents import (
        Block, Chunk,
        _blocks_from_markdown, _chunk_blocks,
    )
    return Block, Chunk, _blocks_from_markdown, _chunk_blocks


def test_markdown_heading_stack():
    """ATX headings build correct breadcrumb; nested headings update the stack."""
    _, _, _blocks_from_markdown, _ = _import_worker()

    md = """# Introduction

Some intro text.

## Background

Background text here.

### Prior work

Prior work details.

## Methods

Methods content.
"""
    blocks = _blocks_from_markdown(md)
    assert blocks, "Expected at least one block"

    # Verify breadcrumbs
    paths = [b.heading_path for b in blocks if b.text.strip()]
    assert ["Introduction"] in paths, f"Expected [Introduction] in {paths}"
    assert ["Introduction", "Background"] in paths, paths
    assert ["Introduction", "Background", "Prior work"] in paths, paths
    assert ["Introduction", "Methods"] in paths, paths
    print("  PASS: markdown heading stack")


def test_markdown_fenced_code_not_heading():
    """# inside a fenced code block must NOT be treated as a heading."""
    _, _, _blocks_from_markdown, _ = _import_worker()

    md = """# Real heading

Text before fence.

```python
# This is a comment, not a heading
def foo():
    pass
```

More text after fence.
"""
    blocks = _blocks_from_markdown(md)
    paths = [b.heading_path for b in blocks]
    # All blocks should be under ["Real heading"], never under ["This is a comment, not a heading"]
    for p in paths:
        assert p == ["Real heading"] or p == [], f"Unexpected path {p}"
    # Code block text must appear somewhere
    all_text = " ".join(b.text for b in blocks)
    assert "def foo" in all_text, "Code block content missing"
    print("  PASS: fenced code not treated as heading")


def test_setext_heading():
    """Setext === / --- headings are detected correctly."""
    _, _, _blocks_from_markdown, _ = _import_worker()

    md = """Title
=====

Introduction
------------

Some body text.
"""
    blocks = _blocks_from_markdown(md)
    paths = [b.heading_path for b in blocks]
    assert ["Title"] in paths or any("Title" in p for p in paths), f"Title heading missing: {paths}"
    print("  PASS: setext heading detection")


def test_chunk_never_crosses_section():
    """No Chunk may mix text from two different heading_paths."""
    _, _, _, _chunk_blocks = _import_worker()
    from workers.documents import Block

    blocks = [
        Block(text="A" * 800, heading_path=["Section 1"], depth=1),
        Block(text="B" * 800, heading_path=["Section 1"], depth=1),
        Block(text="C" * 800, heading_path=["Section 2"], depth=1),
        Block(text="D" * 400, heading_path=["Section 2"], depth=1),
    ]

    chunks = _chunk_blocks(blocks, chunk_chars=1000, chunk_overlap=150)
    assert chunks, "Expected chunks"

    # Verify no chunk mixes paths
    for c in chunks:
        assert c.heading_path in (["Section 1"], ["Section 2"]), \
            f"Chunk has unexpected path: {c.heading_path}"

    # Verify both sections have distinct section_id_ordinals
    s1_ordinals = {c.section_id_ordinal for c in chunks if c.heading_path == ["Section 1"]}
    s2_ordinals = {c.section_id_ordinal for c in chunks if c.heading_path == ["Section 2"]}
    assert s1_ordinals and s2_ordinals, "Both sections must produce chunks"
    assert s1_ordinals.isdisjoint(s2_ordinals), \
        f"Sections share ordinals: {s1_ordinals} ∩ {s2_ordinals}"
    print("  PASS: chunk never crosses section boundary")


def test_overlap_within_section_only():
    """Overlap must occur within a section but not between sections."""
    _, _, _, _chunk_blocks = _import_worker()
    from workers.documents import Block

    # Two distinct sections, each long enough to produce multiple chunks
    blocks = [
        Block(text="X" * 2000, heading_path=["Alpha"], depth=1),
        Block(text="Y" * 2000, heading_path=["Beta"], depth=1),
    ]
    chunks = _chunk_blocks(blocks, chunk_chars=1000, chunk_overlap=200)

    alpha_chunks = [c for c in chunks if c.heading_path == ["Alpha"]]
    beta_chunks  = [c for c in chunks if c.heading_path == ["Beta"]]

    assert len(alpha_chunks) >= 2, "Expected multiple chunks in Alpha section"
    assert len(beta_chunks)  >= 2, "Expected multiple chunks in Beta section"

    # Within Alpha: consecutive chunks must overlap (char ranges share territory)
    for a, b in zip(alpha_chunks, alpha_chunks[1:]):
        assert a.char_end > b.char_start, \
            f"No overlap within Alpha section: {a.char_end} <= {b.char_start}"

    # Last Alpha chunk must end before first Beta chunk starts (no cross-section overlap)
    assert alpha_chunks[-1].char_end <= beta_chunks[0].char_start, \
        "Cross-section overlap detected"
    print("  PASS: overlap within section only, not across boundaries")


def test_char_offsets_global_and_monotonic():
    """char_start / char_end must be monotonically increasing and cover the text."""
    _, _, _, _chunk_blocks = _import_worker()
    from workers.documents import Block

    blocks = [
        Block(text="Hello world this is section one.", heading_path=["S1"], depth=1),
        Block(text="Second section has different content here.", heading_path=["S2"], depth=1),
    ]
    chunks = _chunk_blocks(blocks, chunk_chars=200, chunk_overlap=20)
    assert chunks

    prev_start = -1
    for c in chunks:
        assert c.char_start >= prev_start, \
            f"char_start not monotonic: {c.char_start} after {prev_start}"
        assert c.char_end > c.char_start, "char_end must be > char_start"
        prev_start = c.char_start

    # Reconstruct full text and verify round-trip
    full_text = "\n\n".join(b.text for b in blocks)
    for c in chunks:
        snippet = full_text[c.char_start:c.char_end].strip()
        assert c.text in full_text[c.char_start:c.char_end] or \
               full_text[c.char_start:c.char_end].strip() == c.text, \
            f"Chunk text not found at char_start={c.char_start}..{c.char_end}"
    print("  PASS: char offsets global and monotonic")


def test_pdf_degradation_no_headings():
    """A document with no detectable headings must produce all-flat blocks."""
    _, _, _, _chunk_blocks = _import_worker()
    from workers.documents import Block

    # Simulate what _blocks_from_pdf returns for a document with no headings
    blocks = [
        Block(text="Just some plain paragraph.", heading_path=[], depth=None),
        Block(text="Another paragraph with no structure.", heading_path=[], depth=None),
    ]
    chunks = _chunk_blocks(blocks)
    assert all(c.heading_path == [] for c in chunks), \
        "Flat blocks must produce chunks with empty heading_path"
    print("  PASS: flat blocks produce flat chunks (PDF degradation path)")


# ── DB-backed tests ────────────────────────────────────────────────────────────

async def _run_db_tests(tmp_db: Path) -> None:
    from services import db, documents as doc_service, embeddings

    db.configure_for_tests(tmp_db)
    await db.init_db()
    try:
        await _test_backward_compat_null_sections(db, doc_service, embeddings)
        await _test_heading_searchable_in_fts(db, doc_service, embeddings)
        await _test_neighbour_expansion(db, doc_service, embeddings)
    finally:
        db.shutdown()


async def _test_backward_compat_null_sections(db, doc_service, embeddings):
    """Chunks with NULL section columns must round-trip identically to pre-migration."""
    doc = await doc_service.create("legacy.txt", "text/plain", 100, file_id=None)
    doc_id = doc["id"]

    vec = [0.0] * 256
    await doc_service.add_chunk(
        doc_id, 0, "Legacy chunk text.", vec, 0, 18,
        # No section fields — exactly the old call signature
    )

    rows = await db.fetchall(
        "SELECT * FROM document_chunk WHERE document_id=?", (doc_id,)
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["text"] == "Legacy chunk text."
    assert row["section_id"] is None
    assert row["heading_path"] is None
    assert row["heading"] is None
    print("  PASS: legacy NULL-section chunks preserved correctly")


async def _test_heading_searchable_in_fts(db, doc_service, embeddings):
    """A chunk whose FTS text was prefixed with a heading term should be retrievable
    by that heading term."""
    doc = await doc_service.create("structured.md", "text/markdown", 500, file_id=None)
    doc_id = doc["id"]

    vec = [0.0] * 256
    heading_path = ["Results", "Evaluation"]
    fts_text = " › ".join(heading_path) + "\n" + "The model achieved 94% accuracy."

    await doc_service.add_chunk(
        doc_id, 0, "The model achieved 94% accuracy.", vec, 0, 32,
        heading="Evaluation",
        heading_path=heading_path,
        depth=2,
        section_id=f"{doc_id}:0",
        fts_text=fts_text,
    )

    # FTS query for the heading term
    rows = await db.fetchall(
        "SELECT dc.id FROM document_chunk_fts f "
        "JOIN document_chunk dc ON dc.rowid = f.rowid "
        "WHERE document_chunk_fts MATCH '\"Evaluation\"'"
    )
    ids = [r["id"] for r in rows]
    assert ids, "Heading term 'Evaluation' should be searchable via FTS"
    print("  PASS: heading term is searchable in FTS index")


async def _test_neighbour_expansion(db, doc_service, embeddings):
    """A single winner expands to ≤ 2*radius+1 neighbours within its section only."""
    from services.retrieval import _expand_neighbors, DOC_NEIGHBOR_RADIUS, DOC_MAX_PASSAGE_CHUNKS

    doc = await doc_service.create("expand.md", "text/markdown", 1000, file_id=None)
    doc_id = doc["id"]

    vec = [0.0] * 256
    section_id_a = f"{doc_id}:0"
    section_id_b = f"{doc_id}:1"

    # Section A: 5 chunks
    chunk_ids_a = []
    for i in range(5):
        cid = await doc_service.add_chunk(
            doc_id, i, f"Section A chunk {i}.", vec, i * 100, (i + 1) * 100,
            heading="Section A", heading_path=["Section A"], depth=1,
            section_id=section_id_a,
        )
        chunk_ids_a.append(cid)

    # Section B: 3 chunks
    chunk_ids_b = []
    for i in range(3):
        cid = await doc_service.add_chunk(
            doc_id, i + 5, f"Section B chunk {i}.", vec, (i + 5) * 100, (i + 6) * 100,
            heading="Section B", heading_path=["Section B"], depth=1,
            section_id=section_id_b,
        )
        chunk_ids_b.append(cid)

    # Fetch the winner rows (chunk A[2] wins)
    winner_row = await db.fetchone(
        "SELECT dc.*, d.filename FROM document_chunk dc "
        "JOIN document d ON d.id=dc.document_id WHERE dc.id=?",
        (chunk_ids_a[2],)
    )
    doc_rows = {chunk_ids_a[2]: dict(winner_row)}
    doc_scores = {chunk_ids_a[2]: 0.9}

    expanded_rows, expanded_scores = await _expand_neighbors(
        doc_rows, doc_scores, radius=1, max_passage=3
    )

    assert len(expanded_rows) == 1, f"Expected 1 merged passage, got {len(expanded_rows)}"
    passage = next(iter(expanded_rows.values()))
    # Merged text should contain A[1], A[2], A[3] text (radius=1 → ±1 from winner seq=2)
    assert "Section A chunk 1" in passage["text"], "chunk A[1] should be in passage"
    assert "Section A chunk 2" in passage["text"], "chunk A[2] should be in passage"
    assert "Section A chunk 3" in passage["text"], "chunk A[3] should be in passage"
    assert "Section B" not in passage["text"], "Section B must not bleed into Section A passage"
    print("  PASS: neighbour expansion stays within section, respects radius")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    print("=== test_section_retrieval ===")
    print("--- Pure function tests ---")
    test_markdown_heading_stack()
    test_markdown_fenced_code_not_heading()
    test_setext_heading()
    test_chunk_never_crosses_section()
    test_overlap_within_section_only()
    test_char_offsets_global_and_monotonic()
    test_pdf_degradation_no_headings()

    print("--- DB-backed tests ---")
    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(_run_db_tests(Path(tmp) / "test.db"))

    print("ALL TESTS PASSED")


if __name__ == "__main__":
    # Allow running from project root: python -m scripts.test_section_retrieval
    sys.path.insert(0, str(Path(__file__).parent.parent))
    main()
