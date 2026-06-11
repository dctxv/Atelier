# Memory — the Living Memory System

*How the Atelier remembers things in v2: structured atoms, confidence decay, self-correction, and the prescient jobs that reason forward. Written by Clay.*

---

## What memory is now

In v1, memory was the hub: a flat store of text fragments that chat wrote to and read from. In v2, memory is a **reasoning layer**. Each atom isn't a text blob — it's a subject/predicate/object triple with a predicate category, a polarity, a confidence score, a modality, and a status. The system knows that "Clay prefers Obsidian over Notion" is a *functional* belief (only one value is true at a time), that it might be superseded later, and that it should decay if untouched for long enough. That structure is what makes reconciliation, decay, and hypotheses possible.

The tier system (Basic / Reflective / Prescient) controls which background jobs run. Nothing is extracted until a tier is explicitly selected. See [memory-tier-selection.md](memory-tier-selection.md) for the opt-in flow and gating logic.

---

## The atom — full structure

A v2 atom has two layers: the original v1 fields (text, type, salience, source, timestamps, pinned) that every surface still uses, and the v2 structured fields added as nullable columns. Atoms with null subject/predicate are legacy atoms from before v2. The system handles them gracefully — retrieval treats their confidence as 1.0 with a default decay curve; reconciliation never touches them.

```
memory_atom(
  id, text, type, salience, source_kind, source_id,
  created_at, last_used_at, pinned,

  -- v2 structured fields
  subject            -- "Clay", "work_project", etc.
  predicate          -- "prefers", "works_at", "plans_to", etc.
  predicate_category -- functional | multi_valued | comparative | experiential | attribute
  object             -- the value: "Obsidian", "Anthropic", etc.
  polarity           -- positive | negative | neutral
  intensity          -- 0.0–1.0
  modality           -- factual | desire | plan | commitment | hypothesis | insight
  confidence         -- 0.0–1.0, stored at write time
  valid_from         -- unix timestamp, optional
  valid_until        -- unix timestamp; set on supersession/archival
  temporal_raw       -- original natural-language time phrase, if any
  status             -- active | superseded | retracted | archived
  superseded_by      -- id of the atom that replaced this one
  meta               -- JSON blob for overflow (e.g. coexist_ok, expected_evidence)
)
```

The `status` field is the single source of truth for whether an atom is live. Active atoms participate in retrieval. Superseded, retracted, and archived atoms are excluded from the KNN matrix and from FTS results — but they're never deleted. They form the version history that timeline and audit views walk.

Three supporting tables:

```
memory_event(id, atom_id, kind, detail, created_at)
  -- audit trail: created, corroborated, superseded, retracted, clarified

memory_question(id, kind, atom_ids, prompt_text, status, created_at, resolved_at, resolution)
  -- open questions surfaced in the Review tab

memory_pattern(slot, query_vec, count, last_hit)
  -- query pattern cache for calibration
```

---

## Predicate categories

The category determines how the reconciliation engine treats new facts and how the decay engine ages them.

| Category | Meaning | Decay behavior | Conflict behavior |
|---|---|---|---|
| `functional` | One value at a time. New value supersedes old. | Grace 365d, half-life 365d | New atom supersedes old |
| `multi_valued` | Many values coexist. | Grace 180d, half-life 240d | No conflict; both active |
| `comparative` | Ranking or comparison; new beats old. | Grace 120d, half-life 180d | New atom supersedes old |
| `experiential` | Memory of an event. Never conflicts or decays. | Never decays | Never superseded |
| `attribute` | A property that evolves over time, with valid ranges. | Grace 270d, half-life 365d | Uses valid_from/valid_until ranges |

If no category is set (legacy atoms or atoms without a predicate), the default decay curve applies: 90-day grace, 180-day half-life.

---

## How atoms get created — extraction v2

After a chat turn finishes streaming, the chat router enqueues an `extract_memory` job. This is still the same hot-path rule from v1: extraction is never on the user's path. What changed is everything inside the job.

### Two-level gating

Before the extraction model is ever called, the job runs a significance score over the raw user message. The score is rule-based — no model call: message length, presence of first-person language, preference words, and a penalty for code-heavy messages. Scores run 0–1.

- Below `0.3` (low): skip this turn entirely. No model is called.
- Between `0.3` and `0.7` (ambiguous): call the cheap model with a yes/no "worth extracting?" prompt. Proceed only if yes.
- Above `0.7` (high): extract unconditionally.

This gate catches short messages, commands, follow-up clarifications, and code-heavy turns — all the cases where the extraction model would return `[]` anyway — without paying model cost for them.

### The extraction prompt

When extraction runs, it asks for a structured JSON array of facts, each with the full v2 fields: subject, predicate, predicate_category, object, polarity, intensity, modality, confidence, temporal_raw. It also accepts retraction objects — `{retract: true, text: "..."}` — when the user explicitly corrects or disavows a belief. These become retract operations, not new atoms.

Confidence is capped by modality before writing:

| Modality | Confidence cap |
|---|---|
| factual | 0.95 |
| plan | 0.85 |
| desire | 0.80 |
| hypothesis | 0.60 |

No atom is written with certainty-by-default for inferred or forward-looking beliefs. The caps are enforced in the worker before any DB write.

### Commitment routing

Atoms with `modality=commitment` extracted from *assistant* turns (the model making a promise) don't go into `memory_atom` — they go directly into the `task` table with `source_kind='assistant_commitment'`. The chat context block includes a `[COMMITMENTS]` section showing the three most recent open commitment tasks alongside the memory block. This makes it visible to the model that it committed to something, so it doesn't silently forget.

---

## Reconciliation — dedup, supersession, retraction

Before any new atom is inserted, the reconciliation engine checks for conflicts.

**Dedup:** cosine similarity ≥ 0.92 against active atoms with the same subject+predicate. If a match exists, the existing atom is corroborated (confidence nudged up, `last_used_at` refreshed) instead of inserting a near-duplicate.

**Supersession:** for `functional` and `comparative` predicate categories, if an active atom exists for the same subject+predicate, the new value supersedes the old one. The old atom gets `status='superseded'`, `superseded_by=<new_id>`, and `valid_until=<now>`. The new atom is inserted as active. Both atoms persist — the supersession chain is walkable.

**Retraction:** when the extraction model emits a retraction object, or when the user explicitly retracts from the UI, `retract_atom()` sets `status='retracted'` and `confidence=0.0`. The text stays; the atom is just dead.

Every mutation (supersede, retract, corroborate) bumps `memory_mutation_seq` in `app_config` and writes a row to `memory_event`. Nothing is ever silently lost.

---

## Read-time confidence decay

Decay is never written to the database. It's computed at read time in `_effective_confidence(atom, now_ts)` and applied as a multiplier to the retrieval score. This means there's no background job touching every atom, no write amplification, and no moment where a fact "vanishes" — it just scores lower and lower until it falls below the fading threshold.

The formula:

```
if pinned → stored confidence
if experiential → stored confidence (no decay)
age = now − max(last_used_at, created_at)
if age ≤ grace_period → stored confidence
decay_factor = exp(−ln(2) × (age − grace) / half_life)
effective = max(0.05, stored_confidence × decay_factor)
```

Atoms with `effective_confidence < 0.4` are marked as fading. By default, `retrieve()` excludes fading atoms. The `include_faded=True` flag brings them back — used in the timeline view and the audit trail.

Corroboration does write to the database: when a new fact confirms something already known, `corroborate_atom()` nudges the stored confidence up (`new = min(0.98, old + (0.98 − old) × 0.3)`) and refreshes `last_used_at`. This is the only decay-related write, and it's intentional — facts that keep being mentioned should resist decay.

---

## The uncertainty register — Review tab

Reconciliation sometimes produces genuine conflicts that the system can't resolve: two active atoms for the same subject+predicate with high confidence, neither clearly newer or more authoritative. Rather than silently picking one, the system opens a question.

`services/questions.py` manages the question queue. At most 10 questions can be open at a time. A dismissed question can't reopen for 30 days.

Questions appear in the Review tab of the Memory surface as cards. Each card shows the conflict with both atoms and four resolution buttons:

- **This one** — the chosen atom gets `confidence=0.98`; the other is retracted. Both get a `clarified` event.
- **Both true** — `meta.coexist_ok = true` on both. Reconciliation won't flag them again.
- **Neither** — both atoms are retracted.
- **Dismiss** — closes the question without touching the atoms. Dismissed questions have a 30-day cooldown before the same conflict can reopen.

The Review tab also shows stale-goal questions (from `check_stale_goals`) — "still planning to: X?" for desire and plan atoms untouched for 90+ days.

---

## Goals

Atoms with `modality=desire` or `modality=plan` are the goal graph. The Goals tab queries them separately from the fragment list. Each goal shows its predicate, object, age, and a confidence bar. Goals can be closed from the UI as achieved or dropped — either sets `status='retracted'` and logs the appropriate event. The `close_goal` endpoint writes the closure reason to `meta.closed_reason`.

---

## Hypotheses

The hypothesis engine (prescient tier only) runs weekly and generates up to three silent, falsifiable predictions about near-future facts — things like "Clay will change jobs within 120 days" inferred from a pattern of dissatisfaction plus job-search atoms.

Hypothesis atoms have `modality=hypothesis` and `confidence=0.5`. They are **never injected into chat context**. They don't appear in the normal fragment list. They appear only in a dedicated Hypotheses section in the Review tab. This is intentional: speculative inference has no business being stated as fact in an answer to a question I didn't ask about it.

When a new atom is extracted, `test_hypotheses_against_atom(new_atom)` runs. If the new atom's embedding matches an open hypothesis's `meta.expected_evidence` beyond a cosine threshold, the hypothesis is confirmed: its modality changes to `insight`, confidence rises to 0.85, and a `confirmed` event is logged. Hypotheses also expire at their `valid_until` horizon if never confirmed.

Drift analysis runs quarterly. It walks the supersession chains for `attribute` and self-perception atoms and writes up to three `insight` atoms describing directional changes observed over time. Unlike hypotheses, insight atoms from drift *can* appear in retrieval — they're labeled with modality `insight` and surface as regular atoms in the fragment list.

---

## Timeline and version history

`GET /api/memory/timeline?subject=&predicate=` walks the supersession chain for a given subject+predicate pair. It returns all historical values in order — active at the top, then superseded in reverse-chronological order — each with its `valid_from`, `valid_until`, and confidence at the time.

`GET /api/memory/{id}/events` returns the full audit trail for a single atom: created, corroborated, superseded, retracted, clarified events in sequence.

---

## Background jobs

Four periodic jobs run against the memory system:

**Consolidation** (every 6 hours, all tiers) — the same janitor from v1, extended. Drops exact-duplicate texts, drops orphan atoms whose source session no longer exists, caps growth above 50k, and now also sweeps atoms with a past `valid_until` timestamp to `status='archived'`.

**Calibration** (weekly, all tiers) — reads the `memory_pattern` table to see which kinds of queries actually fire and which atom types they retrieve. Adjusts nothing automatically, but logs a calibration event that the metrics endpoint surfaces.

**Stale goal check** (weekly, reflective + prescient) — scans desire and plan atoms untouched for 90+ days. For each one, opens a `goal_check` question in the uncertainty register if under the 10-question cap.

**Hypothesis generation** (weekly, prescient only) — cheap model generates up to three falsifiable predictions. **Drift analysis** (quarterly, prescient only) — reads supersession chains for attribute atoms and writes narrative insight atoms.

---

## KNN cache correctness

Retrieval keeps an in-memory KNN cache of the active embedding matrix. The v1 version stamp was `(COUNT, MAX_rowid)` — enough to detect inserts and hard deletes, but not in-place mutations like a status flip from `active` to `superseded`. A fact could be retracted, the cache would see the same count and max rowid, and the dead atom would stay in the cosine matrix.

The fix is a `memory_mutation_seq` counter in `app_config`. Every mutation (retract, supersede, corroborate, archive) calls `bump_mutation_seq()` through the single-writer pool. The version stamp is now a 3-tuple: `(COUNT, MAX_rowid, mutation_seq)`. Any in-place mutation invalidates the cache regardless of row count change.

The rebuilt matrix filters `WHERE status='active' OR status IS NULL`, so retracted and superseded atoms never enter the cosine space. The `IS NULL` branch keeps legacy atoms that predate the status column fully participating in retrieval.

---

## The Memory surface — what changed

The Memory surface grew from two panes (fragments + skills) to a four-tab layout:

- **Fragments** — the original view, enhanced with predicate chips, modality badges, and a confidence percentage display for atoms below 70%.
- **Review** — conflict questions and stale-goal questions, each as a card with resolution buttons. A badge shows the count of open questions.
- **Goals** — desire and plan atoms grouped by status, with close buttons.
- **Skills** — unchanged from v1.

The API shape the frontend receives for fragments hasn't changed (the router still maps v2 fields back to the `category`/`timestamp` legacy shape so no existing code broke). The v2 structured fields are included in the response as additional properties; the frontend opts in by reading them.

---

## The full endpoint list

```
GET    /api/memory                        -- fragment list (legacy + v2 fields)
POST   /api/memory                        -- manual add
PUT    /api/memory/{id}                   -- edit text + re-embed
DELETE /api/memory/{id}                   -- hard delete + delete events
POST   /api/memory/{id}/forget            -- same as DELETE, named for the UI
POST   /api/memory/{id}/retract           -- soft retract, keeps history
GET    /api/memory/{id}/events            -- audit trail

GET    /api/memory/questions              -- open/resolved/dismissed questions
POST   /api/memory/questions/{id}/resolve -- resolve a conflict question

GET    /api/memory/timeline               -- ?subject=&predicate= version chain
GET    /api/memory/goals                  -- desire + plan atoms
POST   /api/memory/goals/{id}/close       -- mark achieved or dropped
GET    /api/memory/hypotheses             -- hypothesis atoms (prescient)

GET    /api/memory/export                 -- full JSON dump
POST   /api/memory/story                  -- artistry: narrative synthesis via LLM

GET    /api/memory/tier                   -- { tier_selected, depth }
POST   /api/memory/tier                   -- select/change tier
```

---

## What I didn't build

**Entity / relation graph** — the subject+predicate+object structure is the raw material for one, but I haven't built the `entity` and `relation` tables or a graph view. The data is there; the surface isn't.

**Memory time-travel queries via the UI** — the timeline endpoint exists, but there's no general "what did I believe as of date X" query surface. The timeline is predicate-scoped, not time-scoped.

**Inline clarification during chat** — `get_eligible_clarification()` exists in `services/questions.py` and can identify a conflict worth asking about mid-session, but the chat router doesn't yet surface it inline. Questions go to the Review tab instead.

**Automatic backfill on tier selection** — when you enable memory, it starts from that conversation forward. Past sessions aren't retroactively ingested. See [memory-tier-selection.md](memory-tier-selection.md) for why.

**EmbeddingGemma-300M** — the spec listed it as the preferred local embedding backend. The OpenAI-compatible endpoint option already satisfies "real local embeddings" and requires no model download, so Gemma was deferred. The backend is swappable behind `embed()`, so it's a one-file change when wanted.
