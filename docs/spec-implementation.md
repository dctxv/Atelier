# Atelier — Intelligence & Daily-Driver Spec: Implementation Log

Tracking the build against *Atelier — Intelligence & Daily-Driver Spec* (2026-06-22).
This document is the required pre-implementation deliverable: root-cause
confirmation against the actual code, the dependency-tier view, and the phase
status. It is updated as workstreams land.

---

## 1. Root-cause confirmation (§3 hypotheses vs. the code)

Read before writing: `services/retrieval.py`, `services/intent.py`,
`services/memory.py`, `workers/extraction.py`, `workers/memory_prescient.py`,
`routers/chat.py`, `routers/memory.py`, `static/memory.jsx`, `services/llm.py`,
`services/config.py`.

| # | Hypothesis | Verdict | Notes from the code |
|---|------------|---------|---------------------|
| **P1** | Retrieval is mechanical (vector + BM25 + RRF) with no model of query intent; the regex gate is too blunt. | **Confirmed.** | `retrieve()` fuses numpy-KNN + FTS + docs with RRF and a single global `KNN_MIN_COS = 0.25` floor and fixed `k=12`. The only gate was `intent.memory_relevance()` — a 3-valued regex returning True/False/None, applied *after* retrieval in `chat.py`. Nothing conditioned *which* sources ran or *how tight* the recall was on the query's purpose. → **W1.** |
| **P2** | Extraction is single-message and literal; no corpus-level inference. | **Confirmed.** | `workers/extraction.py` runs significance-gate → single-turn cheap-model extract → per-(subject,predicate) reconcile → atom. There is no pass that reasons *across* atoms. The prescient layer (`workers/memory_prescient.py`) has hypothesis/strand scaffolding but it is hypothesis-testing against new atoms, not corpus-wide pattern/contradiction/evolution inference. → **W2.** |
| **P3** | Memory surface is read-only CRUD; nothing surfaces proactively. | **Confirmed (pending deeper read of `static/memory.jsx`).** | The Memory surface is browse/edit oriented; the prescient panel exists but is not a proactive confirm/reject review queue. → **W3.** |
| **P4** | Chat is a single SSE text path; artifacts are bolted-on. | **Confirmed.** | `routers/chat.py` is one SSE proxy emitting typed events (`card`, `clock`, `docs`, `search`, `provenance`) but no first-class typed *artifact* channel; diagrams ride inline text. → **W4.** |
| **P5** | Tasks is an isolated to-do list, weakly coupled to extraction/retrieval. | **Partially already addressed.** | A thin coupling exists: `extraction._route_commitment()` writes `task` rows with `source_kind='assistant_commitment'`, and `chat.py` injects due commitments as a `[COMMITMENTS]` block. There is no first-class *commitment* object linking idea → task → memory/research, and no confirm step. → **W5.** |
| **P6** | Extraction is invisible/unsteerable; no per-turn accept/reject/edit. | **Confirmed.** | Extraction is fire-and-forget via `jobs.enqueue("extract_memory", …)`. Atoms are editable in the Memory surface but there is no per-turn review of *what this turn produced* with reject-as-signal. → **W6.** |
| **P7** | Projects / Tasks / Email / Export are skeletal. | **Confirmed present, depth TBD.** | Routers + services exist for projects, tasks, email; export is light. Keep/cut is a decision for Clay (§7). → **W7.** |
| **P8** | Voice is half-built and inaccurate. | **Confirmed + removed.** | Server STT (`routers/voice.py`, faster-whisper) + browser `AtelierVoice` (SpeechRecognition/MediaRecorder) + chat composer mic. → **W8 (done).** |

No spec/code contradictions found that change the plan. One nuance flagged: P5
is *further along* than the spec implies (commitment→task plumbing already
exists), which lowers W5's cost if Tasks is kept in W7.

---

## 2. Dependency-tier view (§6)

```
TIER 0  (deck-clearing, no prerequisites)
  W8  remove voice ─────────────────────────────┐ done
  W7  surface triage DECISION (Projects/Tasks/   │ decision only; cuts can
      Email/Export keep-or-cut)                  │ execute immediately
                                                 │
TIER 1  (foundational context gate)              │
  W1  intent-aware retrieval ────────────────────┘ done
        │  (clean mode gate + policies; precision-first)
        ▼
TIER 2  (corpus intelligence, builds on a clean gate)
  W2  inferential memory  ──────────────┐
        │  derived atoms, provenance,    │
        │  Visibility Law                 │
        ▼                                 │
TIER 3  (human-in-the-loop spine)         │
  W6  extraction visibility & steering ◄──┘  (needed to make W2 trustworthy)
        │
        ▼
TIER 4  (proactive surface)
  W3  active / reflexive memory   (needs W2 inferences + W6 steering loop)

INDEPENDENT / LATER
  W5  commitment layer   (gated by the W7 Tasks decision; plumbing partly exists)
  W4  chat artifacts     (lowest priority; confirm artifact type with Clay first)
```

Build order: **W8 + W7-decision → W1 → W2 → W6 → W3 → W5 → W4.**

---

## 3. Global gates (must hold after every workstream)

- Retrieval p95 ≤ ~46.6ms baseline at 50k atoms (`scripts/bench.py`).
- Single-writer integrity: 400 overlapping writes, zero lock errors.
- Hot-path rule: no new blocking work in the user-reply path.

> **Environment note.** The dev container has no configured model endpoint and a
> partial dependency set, so the LLM-backed groups of `scripts/run_tests.py` and
> the seeded-corpus latency run in `scripts/bench.py` must be executed where a
> model + 50k-atom corpus exist. Pure-Python gates (`scripts/test_intent.py`,
> `scripts/test_retrieval_modes.py`) run anywhere and are green.

---

## 4. Phase status

### W8 — Remove voice ✅
Removed cleanly, no adjacent breakage:
- Deleted `routers/voice.py`; unwired import + registration in `app.py`.
- Dropped `faster-whisper` from `requirements.txt`.
- Removed `window.AtelierVoice` (SpeechRecognition + MediaRecorder + `/api/voice/transcribe` client) and the `mic` icon from `static/components.jsx`.
- Removed composer mic button, voice state/refs, the dictation key-guard, the `handleVoiceToggle` handler, and the voice error banner from `static/chat.jsx`.
- Left intact: the unrelated "brand voice"/"meaning and voice" prose strings, and a seed-data atom that merely *mentions* voice (it's user-statement test data, not a code path).
- **Re-introduction note:** to bring voice back, restore a transcription router + a client recorder behind `window.AtelierVoice` and a composer button; nothing else was entangled.

### W1 — Intent-aware retrieval ✅
The headline fix. Retrieval now understands the prompt's cognitive mode and pulls only context that serves it.

- **`services/intent.py`**
  - `retrieval_mode(text, intent)` — Stage-1 regex/heuristic classifier (~0ms) → one of `tool | no_context | factual | technical | exploratory | personal`. Default for the ambiguous residual is `factual` (tight/high-precision), because the observed problem is over-fetching.
  - `classify_mode(text, intent, escalate=…)` — Stage-2 optional cheap-model refinement of the `factual` residual; falls back to Stage-1 on any failure (never blocks a reply).
  - `MODE_POLICIES` — per-mode policy table (lives here so it's importable without numpy and the invariants stay unit-testable). All values `[VALIDATE]`.
  - Legacy `memory_relevance()` retained for back-compat / non-chat callers.
- **`services/retrieval.py`**
  - `retrieve(..., policy=…)` honors the mode policy: gates ambient memory (`inject_memory`), gates docs (`inject_docs`), tunes `k`, per-mode cosine floor `min_cos`, per-mode `budget_tokens`, and `suppress_personal` (drops opinion/desire/trait/self-perception atoms for technical turns).
  - **Pinned atoms are fetched unconditionally** and never dropped by any policy — the suppression gate can never remove protected context.
  - `policy_for(mode)` merges defaults with the `retrieval.mode_policies` app_config JSON override.
  - Backward compatible: `policy=None` reproduces prior behaviour, so the notes co-writer / drafts callers are unaffected.
- **`routers/chat.py`**
  - Computes the mode after `classify()`, fetches the policy, and threads it into `retrieve()`.
  - **Project protection:** when `project_id` is set the policy is forced open (memory + docs on, no personal suppression) — explicitly-scoped context is never gated.
  - Removed the second, after-the-fact `memory_relevance` gate (which risked dropping pinned atoms).
  - Surfaces the chosen `mode` in the `provenance` SSE event (steering/visibility principle).
  - `chat.mode_llm_escalation` config knob (default `False`) controls Stage-2.

**Tests** — `scripts/test_retrieval_modes.py` (pure-Python, green):
- 28-query labelled set across all six modes incl. the headline pollution cases → 100% (bar `[VALIDATE]` ≥ 90%).
- Suppression invariant: `tool` + `no_context` request zero ambient memory.
- Protection invariant: no policy can express pinned/project suppression.
- Policy completeness + precision-ordering (factual tighter than exploratory).

Runtime smoke (with deps): `no_context`/`tool` suppress ambient memory yet still
surface pinned atoms; `technical` keeps a relevant fact atom while dropping a
personal opinion atom; `personal` injects broadly.

**Still owed for W1's full acceptance (need model + corpus):**
- Precision metric (irrelevant-injection rate before/after) on the labelled set.
- End-to-end latency including classification via `scripts/bench.py` (Stage-1 is
  regex/~0ms; Stage-2 stays off by default).

### W2 — Inferential memory ✅ (backend; review UI is W3/W6)
A corpus-level inference pass that reasons *across* the atom corpus — distinct
from the single-message extraction (`workers/extraction.py`) and the
future-prediction hypotheses (`workers/memory_prescient.py`).

- **`workers/memory_inference.py`** — job `infer_memory` (background, never hot
  path). Samples stated facts (excludes existing insights/hypotheses), asks the
  cheap model for patterns / implied preferences / temporal evolution /
  contradictions across the corpus, requires ≥ `min_evidence` distinct sources,
  and mints derived atoms. Degrades silently with no model. Periodic schedule
  registered in `app.py`. Config knobs (all `[VALIDATE]`): `inference_enabled`,
  `inference_max_atoms`, `inference_min_evidence`, `inference_max_new`,
  `inference_cadence_h`.
- **`services/memory.py`** — the derived-atom lifecycle:
  - `add_inference()` mints a *distinct class*: `modality='insight'`,
    `type='inference'`, `status='proposed'`, lower base confidence
    (`INFERENCE_BASE_CONFIDENCE`), provenance in `meta.source_atom_ids`.
    Idempotent (dedups against existing insights by triple or vector similarity).
  - `confirm_inference()` (proposed→active, stays an insight = "believed
    inference"), `reject_inference()` (→rejected, conf 0, kept as signal),
    `list_inferences()`, `provenance()`, `surface_contradiction()` (creates an
    idempotent `memory_question`, never auto-resolves).
- **`services/retrieval.py`** — **Visibility Law enforced structurally**: the
  invariant filter now drops any atom whose `status` is not active/NULL, so a
  proposed/rejected inference can never influence an answer. (Belt-and-braces;
  the KNN cache + FTS already exclude non-active atoms.)
- **`routers/memory.py`** — `/memory/inferred` now also returns
  `proposed_inferences` (with provenance) and open `contradictions`; the existing
  confirm/reject buttons are status-aware (proposed inferences route to the new
  lifecycle); added `GET /memory/{id}/provenance` and `POST /memory/infer`
  (manual trigger).

**Tests** — `scripts/test_inference.py` (DB-backed, no model, green): distinctness,
provenance + deletability (deleting an inference leaves source facts intact),
**Visibility Law** (proposed invisible to retrieval; confirmed becomes
retrievable), idempotency, reject-suppresses, and idempotent contradiction
surfacing. 7/7.

**W2 enhancements (calibrated against Clay's six worked examples):**
- **Confidence accrual (Ex1/Ex6).** A second sighting of an inference no longer
  just dedups — `add_inference` → `_corroborate_inference` raises confidence
  toward `INFERENCE_CORROB_CAP` (never to stated-fact certainty), bumps salience,
  merges the new evidence into provenance, and tracks a `sightings` count. "Low →
  medium, no longer speculative."
- **Reading what wasn't said (Ex2, the headline).** New background job
  `infer_turn` reads the *raw turn* (not just atoms) to catch trigger words
  ("again" → a pattern) and absences/framing ("worth it", no complaint →
  motivation). Enqueued by `extraction.extract_memory` only for significant chat
  turns that produced atoms (cost-bounded), provenance anchored to those atoms,
  first-sighting confidence forced low. Config: `turn_inference_enabled`,
  `turn_inference_min_signif`, `turn_inference_max_new` (all `[VALIDATE]`).
- **Transferable principles (Ex3) + tensions (Ex6).** The corpus prompt now emits
  `principle` (a generalisation distilled from a specific decision) and `tension`
  (a tradeoff to make visible, e.g. motivating work that carries a health cost) —
  distinct from logical `contradiction`. `surface_contradiction(kind=…)` records
  tensions as their own `memory_question` kind; the router lists both.

Mapping to the examples: Ex1 corroboration ✓, Ex2 unsaid/absence ✓ (job +
low-confidence first sighting), Ex3 evolution-not-overwrite ✓ (extraction
supersedes; W2 flags) + principle ✓, Ex4 multi-modality/commitment ✓ (existing),
Ex5 restraint ✓ (gates + ≥2 evidence), Ex6 confidence-rise-on-second-sighting ✓
+ tension surfacing ✓.

**Still owed for W2's full acceptance (need a model):** the inference-*quality*
fixtures (does the cheap model produce the expected derived atoms and avoid
hallucinated ones, including the "again"/absence reads) — runs where a model
endpoint exists. Tests now cover 10 deterministic checks.

> **⚠ Flagged disagreement (per the spec's "flag, don't silently reconcile" rule).**
> The pre-existing prescient layer mints `modality='insight'` atoms at
> `status='active'` (in `_confirm_hypothesis` / `analyze_drift`) — i.e.
> auto-believed *before* the user sees them, which conflicts with W2's Visibility
> Law. W2 introduces the correct `proposed→active` lifecycle for the new corpus
> pass and does **not** retrofit the prescient insights (they're gated behind the
> `prescient` tier, off by default). Recommend a follow-up to route prescient
> insights through the same proposed lifecycle. Not silently changed.

---

### W6 — Extraction visibility & steering ✅
The human-in-the-loop spine that makes inferred memory trustworthy. Clay can see
what each conversation taught the system and correct it; rejections are signal.

- **`services/memory.py`** — steering primitives: `list_unreviewed_facts()` (the
  review queue), `mark_reviewed()` (accept = dismiss, stays believed),
  `add_rejection_signal()` / `is_extraction_suppressed()` (a rejected
  subject·predicate·object is remembered in `app_config` so it isn't re-learned).
- **`workers/extraction.py`** — `_reconcile_before_insert()` now checks the
  suppression list first and returns `skip` for a previously-rejected triple, so
  **a rejection measurably changes future extraction** (the W6 acceptance gate).
  Also enqueues `infer_turn` (W2 per-turn reads) after significant turns.
- **`routers/memory.py`** — `GET /memory/review` (learned facts + proposed
  inferences with provenance), `POST /memory/review/{id}/accept|reject`
  (polymorphic: proposed inferences route through the W2 lifecycle, facts through
  accept/reject). Edit reuses `PUT /memory/{id}`.
- **`static/memory.jsx`** — the living-tier **Review** tab is now the steering
  surface: *Recently learned* (Keep / Edit / Reject), *Proposed inferences*
  (Confirm / Reject, with expandable evidence/provenance), and *To reconcile*
  (existing conflicts/tensions). The tab badge counts learned + proposed + open
  questions. JSX verified to transform via the bundled Babel.

**Tests** — `scripts/test_steering.py` (DB-backed, no model, 4/4): queue surfaces
extraction output, accept dismisses while keeping the fact believed, **rejection
suppresses re-learning in the reconciler**, and rejecting a proposed inference
reuses the W2 lifecycle.

---

### W3 — Active / reflexive memory surfacing ✅
Memory now *pushes* (quietly), not just waits to be browsed. W6 was the pull/review
surface; W3 is the proactive layer on top of the same W2 data.

- **`workers/memory_inference.py`** — added a `connection` inference kind (a
  non-obvious link between facts from different areas) to the corpus prompt.
- **`routers/memory.py`** — `GET /memory/surfacing`: a quiet, ranked digest
  blending newest/highest-confidence proposed inferences with open
  contradictions/tensions; capped (`limit`, default 4) but reports the true
  `total` for the nav signal. Higher-confidence inferences rank first.
- **`static/shell.jsx` + `static/app.jsx`** — a subtle dot on the Memory rail
  icon when `surfacing.total > 0`. Polls slowly (45s), pauses when the tab is
  hidden, re-checks on surface change — informs without nagging.
- **`static/memory.jsx`** — an **Active memory** panel at the top of Overview
  (renders only when there's something to say) showing up to 3 items with inline
  Confirm/Reject for inferences and a "Reconcile in Review" link for conflicts,
  plus a "+N more in Review" affordance. JSX verified via bundled Babel.

**Tests** — `scripts/test_surfacing.py` (DB-backed, no model, 4/4): blends
inferences + conflicts into a total, capped/quiet, confidence-ranked, conflicts
carry their type. All five pure-Python/DB suites green together.

---

## 4a. W7 surface triage — DECISION (confirmed with Clay)

| Surface | Call | Rationale |
|---------|------|-----------|
| **Tasks** | **KEEP** | Becomes the spine of the W5 commitment layer; commitment→task plumbing already exists. |
| **Projects** | **CUT** | No named daily use. |
| **Email** | **CUT** | No named daily use. |
| **Export** | **CUT** | No named daily use. |

Cuts will be executed as a dedicated change (clean removal, no broken
routes/JSX) per the W7 acceptance gate, sequenced with W5.

---

## 5. Open questions for Clay (gate later phases, not W1/W8)

1. **W1 tuning:** confirm the six-mode set and the precision/recall defaults in
   `MODE_POLICIES` once measured against real failure cases.
2. **W7 keep-or-cut:** Projects, Tasks, Email, Export — decide before building
   W4/W5 breadth. (Tasks likely *keep* as the W5 spine; commitment→task plumbing
   already exists.)
3. **W4 artifact type:** which single artifact type matters most for daily use.
4. **Contextual Retrieval:** fold contextual-chunk prepending into W1's relevance
   push, or keep it a separate Documents-pipeline change.
