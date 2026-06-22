"""W3 — active / reflexive memory surfacing.

DB-backed, no model. Validates the quiet proactive digest that feeds the nav dot
and the Overview 'Active memory' panel: it blends proposed inferences with open
contradictions/tensions, is capped (quiet), reports a true total, and ranks
higher-confidence inferences first.

Run:  python -m scripts.test_surfacing
"""
import asyncio

from services import db, memory


async def _fact(text, predicate):
    return await memory.add_atom(text, type_="fact", source_kind="test_run",
                                 subject="user", predicate=predicate)


async def run():
    await db.init_db()
    passed = []

    def ok(name):
        passed.append(name)
        print(f"  PASS: {name}")

    # Build a server stub to call the router fn directly (no HTTP).
    from routers.memory import get_surfacing

    # Empty-ish baseline (ignore any pre-existing): record baseline total.
    base = await get_surfacing(limit=4)
    base_total = base["total"]

    # Seed two proposed inferences with different confidence + a contradiction.
    s1 = await _fact("Clay shipped at 2am Monday", "worked_late")
    s2 = await _fact("Clay shipped at 1am Friday", "worked_late")
    low = await memory.add_inference("Clay might prefer mornings", [s1["id"], s2["id"]],
                                     kind="implied_preference", subject="user",
                                     predicate="prefers", object_val="mornings", confidence=0.35)
    high = await memory.add_inference("Clay works late at night", [s1["id"], s2["id"]],
                                      kind="pattern", subject="user",
                                      predicate="work_rhythm", object_val="night", confidence=0.8)
    c1 = await _fact("Clay lives in Sydney", "lives_in")
    c2 = await _fact("Clay lives in Perth", "lives_in")
    qid = await memory.surface_contradiction([c1["id"], c2["id"]],
                                             "Sydney vs Perth?", kind="contradiction")

    d = await get_surfacing(limit=4)

    # total reflects the new items (2 inferences + 1 conflict).
    assert d["total"] == base_total + 3, (d["total"], base_total)
    assert d["counts"]["inferences"] >= 2 and d["counts"]["conflicts"] >= 1
    ok("surfacing blends proposed inferences + open conflicts into a total")

    # Quiet: capped to `limit`.
    assert len(d["items"]) <= 4
    ok("digest is capped (quiet by default)")

    # Ranking: among inference items, higher confidence comes before lower.
    inf_items = [i for i in d["items"] if i["type"] == "inference"]
    confs = [i["confidence"] for i in inf_items if i["confidence"] is not None]
    assert confs == sorted(confs, reverse=True), confs
    assert any(i["id"] == high["id"] for i in inf_items), "high-confidence inference not surfaced"
    ok("higher-confidence inferences rank first")

    # Conflict item carries its type for the panel to label/route.
    assert any(i["type"] == "contradiction" for i in d["items"])
    ok("contradictions surface with their type for the panel")

    # cleanup
    for aid in (s1["id"], s2["id"], low["id"], high["id"], c1["id"], c2["id"]):
        await memory.delete_atom(aid)
    await db.execute("DELETE FROM memory_question WHERE id=?", (qid,))

    print(f"\nAll W3 surfacing tests passed! ({len(passed)} checks)")


if __name__ == "__main__":
    asyncio.run(run())
