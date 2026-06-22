"""W2 — inferential memory: derived-atom lifecycle, Visibility Law, provenance.

DB-backed (uses the real single-writer + numpy KNN) but needs NO model — it
exercises the deterministic spine of W2: distinctness, provenance, deletability,
the Visibility Law (proposed inferences never influence retrieval), idempotency,
and contradiction surfacing. The inference-quality test (does the cheap model
produce the *right* derived atoms) needs a model endpoint and lives with the
LLM-backed suite.

Run:  python -m scripts.test_inference
"""
import asyncio

from services import db, memory, retrieval


async def _seed_fact(text, subject="user", predicate="works_at_night"):
    return await memory.add_atom(
        text, type_="fact", source_kind="test_run",
        subject=subject, predicate=predicate, predicate_category="multi_valued",
        modality="factual", confidence=0.9,
    )


async def run():
    await db.init_db()
    passed = []

    def ok(name):
        passed.append(name)
        print(f"  PASS: {name}")

    # ── Seed source facts ────────────────────────────────────────────────────
    a1 = await _seed_fact("Clay pushed commits at 2am on Monday")
    a2 = await _seed_fact("Clay replied to email at 1:30am on Thursday")
    src_ids = [a1["id"], a2["id"]]

    # ── 1. Distinctness ───────────────────────────────────────────────────────
    inf = await memory.add_inference(
        "Clay tends to work late at night", source_atom_ids=src_ids,
        kind="pattern", subject="user", predicate="work_rhythm", object_val="night",
    )
    assert inf is not None
    assert inf["modality"] == "insight", inf["modality"]
    assert inf["type"] == "inference", inf["type"]
    assert inf["status"] == "proposed", inf["status"]
    assert (inf.get("meta") or {}).get("inference") is True
    assert inf["confidence"] == memory.INFERENCE_BASE_CONFIDENCE
    ok("derived atom is a distinct class (insight/inference/proposed, lower confidence)")

    # ── 2. Provenance + deletability ─────────────────────────────────────────
    prov = await memory.provenance(inf["id"])
    assert {p["id"] for p in prov} == set(src_ids), prov
    # Deleting the derived atom must not destroy the source facts.
    await memory.delete_atom(inf["id"])
    assert await memory.get_atom(a1["id"]) is not None
    assert await memory.get_atom(a2["id"]) is not None
    ok("provenance links to sources; deleting the inference leaves facts intact")

    # ── 3. Visibility Law ─────────────────────────────────────────────────────
    inf2 = await memory.add_inference(
        "Clay tends to work late at night", source_atom_ids=src_ids,
        kind="pattern", subject="user", predicate="work_rhythm", object_val="night",
    )
    res = await retrieval.retrieve("when does Clay work, late night rhythm")
    assert not any(r["id"] == inf2["id"] for r in res), \
        "proposed inference leaked into retrieval (Visibility Law violated)"
    ok("proposed inference is invisible to retrieval")

    # confirm → believed → now visible
    await memory.confirm_inference(inf2["id"])
    confirmed = await memory.get_atom(inf2["id"])
    assert confirmed["status"] == "active"
    assert confirmed["modality"] == "insight"  # still an inference, just believed
    res2 = await retrieval.retrieve("Clay tends to work late at night")
    assert any(r["id"] == inf2["id"] for r in res2), \
        "confirmed inference did not become retrievable"
    ok("confirmed inference becomes believed + retrievable, still tagged insight")

    # ── 4. Idempotency + confidence accrual (Ex1/Ex6) ─────────────────────────
    a3 = await _seed_fact("Clay was online coding at 2:45am on Saturday")
    before = await db.fetchone(
        "SELECT COUNT(*) AS n FROM memory_atom WHERE modality='insight'")
    conf_before = (await memory.get_atom(inf2["id"]))["confidence"]
    dup = await memory.add_inference(
        "Clay tends to work late at night", source_atom_ids=[a1["id"], a3["id"]],
        kind="pattern", subject="user", predicate="work_rhythm", object_val="night",
    )
    after = await db.fetchone(
        "SELECT COUNT(*) AS n FROM memory_atom WHERE modality='insight'")
    assert dup["id"] == inf2["id"], "re-inferring created a different atom"
    assert before["n"] == after["n"], "re-running the pass duplicated an inference"
    ok("re-inferring the same thing is idempotent (no duplicate)")

    assert dup["confidence"] > conf_before, \
        f"confidence did not rise on re-sighting ({conf_before} -> {dup['confidence']})"
    assert dup["confidence"] <= memory.INFERENCE_CORROB_CAP
    prov_ids = {p["id"] for p in await memory.provenance(inf2["id"])}
    assert a3["id"] in prov_ids, "new evidence not merged into provenance"
    assert (dup.get("meta") or {}).get("sightings", 0) >= 2
    ok("second sighting corroborates: confidence rises, evidence merges (Ex1/Ex6)")

    # ── 5. Reject suppresses ──────────────────────────────────────────────────
    inf3 = await memory.add_inference(
        "Clay prefers tabs over spaces", source_atom_ids=src_ids, kind="implied_preference",
        subject="user", predicate="prefers", object_val="tabs",
    )
    await memory.reject_inference(inf3["id"])
    rej = await memory.get_atom(inf3["id"])
    assert rej["status"] == "rejected" and rej["confidence"] == 0.0
    res3 = await retrieval.retrieve("Clay prefers tabs over spaces")
    assert not any(r["id"] == inf3["id"] for r in res3)
    ok("rejected inference is suppressed from retrieval")

    # ── 6. Contradiction surfacing (idempotent, no auto-resolve) ──────────────
    c1 = await _seed_fact("Clay lives in Sydney", predicate="lives_in")
    c2 = await _seed_fact("Clay lives in Melbourne", predicate="lives_in")
    qid = await memory.surface_contradiction(
        [c1["id"], c2["id"]], "Clay lives in Sydney vs Melbourne — which is current?")
    assert qid is not None
    again = await memory.surface_contradiction([c1["id"], c2["id"]], "dup")
    assert again is None, "contradiction surfaced twice for the same atom set"
    row = await db.fetchone("SELECT * FROM memory_question WHERE id=?", (qid,))
    assert row["kind"] == "contradiction" and row["status"] == "open"
    ok("contradiction surfaced once for reconciliation (no auto-resolve)")

    # ── 7. Tension (tradeoff, not logical conflict) surfaces distinctly (Ex6) ──
    t1 = await _seed_fact("Clay feels stressed lately", predicate="feels")
    t2 = await _seed_fact("Clay attributes stress to late nights on Atelier",
                          predicate="attributes_stress_to")
    tqid = await memory.surface_contradiction(
        [t1["id"], t2["id"]], "Motivating work also carries a health cost.",
        kind="tension")
    assert tqid is not None
    trow = await db.fetchone("SELECT kind FROM memory_question WHERE id=?", (tqid,))
    assert trow["kind"] == "tension"
    ok("tension surfaced as a distinct kind (tradeoff, not auto-resolved)")

    # ── 8. Per-turn 'read the unsaid' job is registered (Ex2 plumbing) ─────────
    from workers import memory_inference  # noqa: F401 (registers handlers)
    from workers import jobs
    assert "infer_turn" in jobs._handlers, "infer_turn job not registered"
    assert "infer_memory" in jobs._handlers, "infer_memory job not registered"
    ok("per-turn + corpus inference jobs are registered")

    # ── cleanup test_run + inference atoms ────────────────────────────────────
    for aid in (a1["id"], a2["id"], a3["id"], c1["id"], c2["id"],
                t1["id"], t2["id"], inf2["id"], inf3["id"]):
        await memory.delete_atom(aid)
    await db.execute("DELETE FROM memory_question WHERE id IN (?,?)", (qid, tqid))

    print(f"\nAll W2 inference tests passed! ({len(passed)} checks)")


if __name__ == "__main__":
    asyncio.run(run())
