"""W5 - commitment layer.

DB-backed, no model. Validates the trust boundary: extraction proposes a
commitment, but no task is created until the user confirms it. Confirming links
commitment -> task -> source atom; rejecting leaves no task behind.

Run:  python -m scripts.test_commitments
"""
import asyncio

from services import commitments, db, memory, tasks
from workers.extraction import _route_commitment


async def run():
    await db.init_db()
    passed = []

    def ok(name):
        passed.append(name)
        print(f"  PASS: {name}")

    session_id = "sess-test-w5"
    atom = await memory.add_atom(
        "Clay will build the commitment layer after the retrieval fix",
        type_="fact",
        source_kind="chat",
        source_id=session_id,
        subject="user",
        predicate="plans_to_build",
        predicate_category="multi_valued",
        object_val="commitment layer",
        modality="commitment",
        confidence=0.82,
    )

    await _route_commitment(
        atom,
        session_id,
        "I am building the commitment layer after the retrieval fix.",
        "Good, I will track that.",
    )
    proposed = await commitments.list_commitments(status="proposed")
    proposal = next((c for c in proposed if c.get("atom_id") == atom["id"]), None)
    assert proposal is not None, "commitment was not proposed"
    assert proposal["task_id"] is None, "task was silently created before confirmation"
    task_rows = await db.fetchall(
        "SELECT * FROM task WHERE source_kind='commitment' AND source_id=?",
        (proposal["id"],),
    )
    assert task_rows == [], "task row exists before confirmation"
    ok("extraction creates a proposed commitment, not a silent task")

    confirmed = await commitments.confirm(proposal["id"])
    assert confirmed and confirmed["status"] == "active", confirmed
    assert confirmed["task_id"], "confirmed commitment did not link a task"
    task = await db.fetchone("SELECT * FROM task WHERE id=?", (confirmed["task_id"],))
    assert task and task["source_kind"] == "commitment"
    assert task["source_id"] == proposal["id"]
    ok("confirm creates and links the task")

    await commitments.confirm(proposal["id"])
    dup_tasks = await db.fetchall(
        "SELECT * FROM task WHERE source_kind='commitment' AND source_id=?",
        (proposal["id"],),
    )
    assert len(dup_tasks) == 1, "confirming twice created duplicate tasks"
    ok("confirm is idempotent")

    await tasks.update(confirmed["task_id"], {"status": "done"})
    done = await commitments.get(proposal["id"])
    assert done["status"] == "done", done["status"]
    ok("completing the task closes the commitment")

    atom2 = await memory.add_atom(
        "Clay will test an unwanted proposal",
        type_="fact",
        source_kind="chat",
        source_id=session_id,
        subject="user",
        predicate="plans_to_test",
        predicate_category="multi_valued",
        object_val="unwanted proposal",
        modality="commitment",
        confidence=0.7,
    )
    reject_me = await commitments.propose_from_atom(atom2, session_id)
    rejected = await commitments.reject(reject_me["id"])
    assert rejected and rejected["status"] == "rejected"
    reject_tasks = await db.fetchall(
        "SELECT * FROM task WHERE source_kind='commitment' AND source_id=?",
        (reject_me["id"],),
    )
    assert reject_tasks == [], "rejecting a proposal created a task"
    ok("reject suppresses the proposal without creating a task")

    # cleanup
    for aid in (atom["id"], atom2["id"]):
        await memory.delete_atom(aid)
    await db.execute(
        "DELETE FROM task WHERE source_kind='commitment' AND source_id IN (?,?)",
        (proposal["id"], reject_me["id"]),
    )
    await db.execute(
        "DELETE FROM commitment WHERE id IN (?,?)",
        (proposal["id"], reject_me["id"]),
    )

    print(f"\nAll W5 commitment tests passed! ({len(passed)} checks)")


if __name__ == "__main__":
    asyncio.run(run())
