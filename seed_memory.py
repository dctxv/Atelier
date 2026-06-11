"""Seed sample memory atoms for the user.

Run once after the app has been started at least once (so the DB and schema exist):
    python seed_memory.py

Safe to re-run — uses dedup=True so nothing doubles up.
"""
from __future__ import annotations

import asyncio
import sys
import time

sys.path.insert(0, ".")


async def main():
    from services import db, memory, config

    await db.init_db()

    # Set tier to prescient so all tabs are visible
    await config.set_setting("memory.tier", "prescient")
    await config.set_setting("memory.tier_selected", "true")

    now = int(time.time())
    month = 30 * 86400

    atoms = [
        # ── Identity ──────────────────────────────────────────────────────────
        dict(text="My name is dctxv", subject="user", predicate="name",
             predicate_category="attribute", modality="factual", confidence=0.98,
             valid_from=now - 12 * month),

        dict(text="I'm a software developer", subject="user", predicate="occupation",
             predicate_category="attribute", modality="factual", confidence=0.95,
             valid_from=now - 24 * month),

        dict(text="I'm building Atelier — a personal AI assistant with a living memory system",
             subject="user", predicate="working_on", predicate_category="commitment",
             modality="factual", confidence=0.98, valid_from=now - 6 * month),

        dict(text="I care deeply about privacy-first AI that runs locally",
             subject="user", predicate="values", predicate_category="attribute",
             modality="self_perception", confidence=0.90, valid_from=now - 8 * month),

        dict(text="I prefer clean, minimal UI design with warm typographic palettes",
             subject="user", predicate="aesthetic_preference", predicate_category="attribute",
             modality="self_perception", confidence=0.85, valid_from=now - 5 * month),

        # ── Career / projects ──────────────────────────────────────────────────
        dict(text="I'm the sole developer on Atelier — designing and implementing everything myself",
             subject="user", predicate="job_title", predicate_category="attribute",
             modality="factual", confidence=0.97, valid_from=now - 6 * month),

        dict(text="I shipped Living Memory System v2 for Atelier — structured atoms, KNN retrieval, reconciliation",
             subject="user", predicate="shipped", predicate_category="commitment",
             modality="factual", confidence=0.99, valid_from=now - 1 * month),

        dict(text="I'm implementing Prescient Memory Part 1 — strands, hypothesis engine, weekly diff",
             subject="user", predicate="working_on", predicate_category="commitment",
             modality="factual", confidence=0.97, valid_from=now - 7 * 86400),

        dict(text="I use FastAPI + SQLite + numpy for the backend; React (no bundler) for the frontend",
             subject="user", predicate="tech_stack", predicate_category="attribute",
             modality="factual", confidence=0.95, valid_from=now - 6 * month),

        dict(text="I want Atelier to eventually replace all the scattered tools I use for thinking and planning",
             subject="user", predicate="goal", predicate_category="desire",
             modality="desire", confidence=0.88, valid_from=now - 4 * month),

        # ── Goals / aspirations ────────────────────────────────────────────────
        dict(text="I want memory to feel invisible and correct — never jarring the user with wrong recalls",
             subject="user", predicate="goal", predicate_category="desire",
             modality="desire", confidence=0.92, valid_from=now - 3 * month),

        dict(text="I'm planning to add voice input and output to Atelier",
             subject="user", predicate="plan", predicate_category="plan",
             modality="plan", confidence=0.75, valid_from=now - 2 * month),

        dict(text="I want to open-source parts of Atelier once the memory system is stable",
             subject="user", predicate="aspiration", predicate_category="desire",
             modality="desire", confidence=0.70, valid_from=now - 5 * month),

        # ── Preferences / working style ────────────────────────────────────────
        dict(text="I prefer iterative, design-doc-driven development — writing specs before code",
             subject="user", predicate="work_style", predicate_category="attribute",
             modality="self_perception", confidence=0.88, valid_from=now - 10 * month),

        dict(text="I like working late at night when it's quiet",
             subject="user", predicate="habit", predicate_category="experiential",
             modality="factual", confidence=0.80, valid_from=now - 8 * month),

        dict(text="I use Claude heavily for pair-programming and architecture discussions",
             subject="user", predicate="tool_preference", predicate_category="attribute",
             modality="factual", confidence=0.95, valid_from=now - 3 * month),

        dict(text="I find long planning documents clarify my thinking even when I don't follow them exactly",
             subject="user", predicate="learning_style", predicate_category="attribute",
             modality="self_perception", confidence=0.82, valid_from=now - 6 * month),

        # ── Health / wellbeing ─────────────────────────────────────────────────
        dict(text="I try to take regular breaks but often get absorbed in deep work sessions",
             subject="user", predicate="habit", predicate_category="experiential",
             modality="self_perception", confidence=0.78, valid_from=now - 4 * month),

        # ── Inferred / hypothesis (prescient tier) ─────────────────────────────
        dict(text="I may be optimising for a 1-person product that scales without a team",
             subject="user", predicate="inferred_goal", predicate_category="desire",
             modality="hypothesis", confidence=0.60, valid_from=now - 2 * month,
             meta={
                 "generation_pattern": "goal_implication",
                 "supporting_evidence": "Building everything solo; privacy-first; no bundler/framework dependencies",
                 "disconfirming_evidence": "Mentioned open-sourcing — implies community involvement",
                 "days_ttl": 60,
                 "observations": [],
             }),

        dict(text="I value correctness guarantees over feature velocity in the memory system",
             subject="user", predicate="inferred_value", predicate_category="attribute",
             modality="hypothesis", confidence=0.72, valid_from=now - 1 * month,
             meta={
                 "generation_pattern": "extrapolation",
                 "supporting_evidence": "Detailed invariant documentation; explicit [VALIDATE] markers; benchmark requirements",
                 "disconfirming_evidence": "Shipped v2 in a single session — fast iteration suggests velocity matters too",
                 "days_ttl": 45,
                 "observations": [],
             }),

        # ── Inferred facts (insight modality) ─────────────────────────────────
        dict(text="Atelier is likely dctxv's primary personal project given depth and sustained commitment",
             subject="Atelier", predicate="project_status", predicate_category="attribute",
             modality="insight", confidence=0.85, valid_from=now - 14 * 86400),
    ]

    added = 0
    for kwargs in atoms:
        kwargs.setdefault("type_", "fact")
        kwargs.setdefault("source_kind", "manual")
        kwargs.setdefault("salience", 1.0)
        kwargs.setdefault("dedup", True)
        try:
            await memory.add_atom(**kwargs)
            added += 1
        except Exception as e:
            print(f"  skip: {kwargs['text'][:60]!r} — {e}")

    print(f"Seeded {added}/{len(atoms)} memory atoms.")
    print("Tier set to: prescient")
    db.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
