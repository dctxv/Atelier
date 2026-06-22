"""W1 — intent-aware retrieval: labelled query set + gate invariants.

Pure-Python (no server, no model, no numpy) so it runs anywhere the stdlib does.
It validates Stage-1 cognitive-mode classification and the policy invariants that
the spec's acceptance gates depend on. The latency / precision-at-scale gates that
need a running server + seeded corpus live in scripts/bench.py and
scripts/run_tests.py.

Run:  python -m scripts.test_retrieval_modes
"""
from services.intent import (
    retrieval_mode, classify, MODE_POLICIES, RETRIEVAL_MODES,
)

# ── Labelled query set ────────────────────────────────────────────────────────
# (query, expected_mode). Includes the real failure cases the spec calls out:
# impersonal/world-knowledge prompts that were polluting context with personal
# memory must land in no_context (zero ambient memory).
CASES: list[tuple[str, str]] = [
    # tool — deterministic local answer, retrieve nothing
    ("what is 47 * 89?",                         "tool"),
    ("100 km to miles",                          "tool"),
    ("what time is it in Tokyo?",                "tool"),
    ("$AAPL",                                    "tool"),
    ("weather in Sydney",                        "tool"),

    # no_context — generic world-knowledge / generation, no personal signal
    ("what is a monad",                          "no_context"),
    ("explain how async/await works",            "no_context"),
    ("define recursion",                         "no_context"),
    ("who is Ada Lovelace",                      "no_context"),
    ("translate hello into French",              "no_context"),
    ("write a function to reverse a string",     "no_context"),
    ("what is the difference between TCP and UDP", "no_context"),  # headline pollution case
    ("explain the transformer architecture",     "no_context"),   # headline pollution case

    # technical — code / debugging
    ("I'm getting a TypeError in my python script", "technical"),
    ("how do I fix this stack trace",            "technical"),
    ("debug my regex for email validation",      "technical"),
    ("write a python function to sort a list",   "technical"),
    ("why is my docker container crashing",      "technical"),

    # exploratory — brainstorming / open-ended thinking
    ("brainstorm marketing angles for a coffee shop", "exploratory"),
    ("let's explore options for the architecture",    "exploratory"),
    ("give me some ideas for a weekend trip",         "exploratory"),
    ("pros and cons of remote work",                  "exploratory"),

    # personal — reflection or explicit memory request
    ("what do you know about me",                "personal"),
    ("remember that I prefer tabs over spaces",  "personal"),
    ("based on what you know, what should I focus on", "personal"),
    ("recommend a book for me",                  "personal"),

    # factual — tight, high-precision residual (may be personal)
    ("remind me what we set the threshold to",   "factual"),
    ("flight time from sydney to melbourne",     "factual"),
]


def test_classification():
    wrong = []
    for q, expected in CASES:
        got = retrieval_mode(q, classify(q))
        if got != expected:
            wrong.append((q, expected, got))
    total = len(CASES)
    acc = (total - len(wrong)) / total
    print(f"  classification accuracy: {total - len(wrong)}/{total} = {acc:.0%}")
    for q, exp, got in wrong:
        print(f"    [MISS] {q!r}: expected {exp}, got {got}")
    # [VALIDATE] pass bar — tighten as the labelled set grows.
    assert acc >= 0.90, f"mode accuracy {acc:.0%} below 90% bar"
    print("  PASS: classification")


def test_suppression_invariant():
    """no_context and tool inject ZERO ambient personal memory (pinned excepted,
    which retrieve() handles outside the policy)."""
    for mode in ("tool", "no_context"):
        pol = MODE_POLICIES[mode]
        assert pol["inject_memory"] is False, f"{mode} must not inject ambient memory"
        assert pol["k"] == 0, f"{mode} must request zero ambient memory candidates"
    print("  PASS: tool + no_context suppress ambient memory")


def test_protection_invariant():
    """The policy never carries any flag that would drop pinned/project atoms —
    that protection is structural in retrieve() (pinned fetched unconditionally;
    project context forced on in chat.py), never expressible as a policy knob."""
    for mode, pol in MODE_POLICIES.items():
        assert "suppress_pinned" not in pol
        assert "suppress_project" not in pol
        # suppress_personal only ever applies to technical mode by default
        if pol.get("suppress_personal"):
            assert mode == "technical", f"unexpected suppress_personal on {mode}"
    print("  PASS: no policy can suppress pinned/project context")


def test_policy_completeness():
    for mode in RETRIEVAL_MODES:
        assert mode in MODE_POLICIES, f"missing policy for {mode}"
        for key in ("inject_memory", "inject_docs", "k", "min_cos",
                    "budget_tokens", "suppress_personal"):
            assert key in MODE_POLICIES[mode], f"{mode} missing {key}"
    print("  PASS: every mode has a complete policy")


def test_precision_ordering():
    """Precision-leaning default: high-precision modes use a higher cosine floor
    and a smaller candidate count than associative modes."""
    assert MODE_POLICIES["factual"]["min_cos"] > MODE_POLICIES["exploratory"]["min_cos"]
    assert MODE_POLICIES["factual"]["k"] < MODE_POLICIES["exploratory"]["k"]
    assert MODE_POLICIES["technical"]["suppress_personal"] is True
    print("  PASS: precision ordering (factual tighter than exploratory)")


if __name__ == "__main__":
    print("W1 — intent-aware retrieval gate")
    test_classification()
    test_suppression_invariant()
    test_protection_invariant()
    test_policy_completeness()
    test_precision_ordering()
    print("\nAll W1 mode-gate tests passed!")
