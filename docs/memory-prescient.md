# Memory — Prescient Tier (P1.0–P1.6)

*The second phase of the Living Memory build: strands, suppression, warming, hypothesis v2, and the weekly digest. Written by Clay.*

---

## What this doc covers

The original memory doc covers the atom schema, reconciliation, decay, and the v2 background jobs through the baseline prescient tier. This document covers the P1 build: seven phases that flesh out what "prescient" actually means in practice. The phases can be read independently but they're designed as a coherent layer — suppression and strand clustering inform hypothesis generation, warming depends on goals and patterns accumulated from retrieval, and the weekly diff pulls thread from all of them.

---

## P1.0 — Three-tier capability gate

### Why a gate at all

The original tier names in the design doc were Basic / Reflective / Prescient. By the time the code shipped, those had been renamed **essential / living / prescient** to better express what each tier provides rather than what it implies about capability. Essential means the minimum viable system — just atoms and retrieval, no background reasoning. Living means a maintained, evolving model of yourself. Prescient means the system starts making predictions and protecting you from its own obsolescence.

The gate exists because background jobs have real costs: model calls, extra DB writes, wall-clock latency for NLI checks. None of these should run unless the user has deliberately opted into a tier. See [memory-tier-selection.md](memory-tier-selection.md) for the opt-in flow.

### How the gate works

`services/config.py` contains the entire gating logic in about 20 lines:

```python
_TIER_ORDER = {"essential": 0, "living": 1, "prescient": 2}
_CAP_TIER: dict[str, str] = {
    "structured":       "living",
    "reconciliation":   "living",
    "review":           "living",
    "timelines":        "living",
    "goals":            "living",
    "commitments":      "living",
    "warming_basic":    "living",
    "strands":          "prescient",
    "stale_guard":      "prescient",
    "negative_space":   "prescient",
    "warming":          "prescient",
    "hypothesis":       "prescient",
    "weekly_diff":      "prescient",
}

async def tier_allows(capability: str) -> bool:
    current = (await get_setting("memory.tier") or "living").strip().lower()
    required = _CAP_TIER.get(capability, "living")
    return _TIER_ORDER.get(current, 1) >= _TIER_ORDER.get(required, 1)
```

The current tier is stored as `memory.tier` in `app_config`. The default is `'living'`. `tier_allows()` takes a capability name as a string, looks it up in `_CAP_TIER`, and compares the tier order integers. Unknown capabilities default to the living tier requirement — a safe fallback that doesn't silently enable prescient features.

The design here was intentional: this is not a feature flag system and it's not a permissions system. It's an expression of what background jobs are *appropriate* given the user's expressed intent about how deeply the system should reason about them. Capability names like `'negative_space'` and `'stale_guard'` describe the semantic function, not the code path — that keeps call sites readable.

### New LLM task tiers

Four new task identifiers were added to `services/llm.py`, all mapped to `'cheap'` model routing:

| Task | Used by |
|---|---|
| `strand_cluster` | `propose_strand_clusters()` (reserved for future semantic clustering) |
| `hypothesis_generation` | `generate_hypotheses()` weekly job |
| `hypothesis_nli` | `_nli_call()` in hypothesis testing |
| `weekly_diff_summary` | `generate_weekly_diff()` weekly job |

All four are cheap because they're run in background jobs, not on the user's hot path. The `strand_cluster` task name exists in the registry even though the current clustering is lexical, not model-driven — it's a placeholder so the routing table is correct when semantic clustering is wired in.

---

## P1.1 — Strand timelines

### What strands are

A strand is a named life-area timeline: a bundle of predicates (and optionally subjects) whose matching atoms are aggregated into a single view. "Career" collects everything about your employer, job title, and current work. "Health" collects exercise, sleep, diet, symptoms, injuries. The point is not deduplication — it's grouping scattered atoms into a coherent timeline with a span: "I've worked on this since March 2024."

Atoms can belong to multiple strands. `working_on` is in both Career and Projects. That's correct — a project you're working on *is* a career fact. Multi-membership is a feature, not a bug.

Strands are entirely a UI surface. They are never injected into chat context. The code comment at the top of `services/strands.py` states this as a law: *"Strand metadata is never injected into chat; it is a UI-only surface."* The reasoning: strand membership is a derived view, and derived views have no place in a chat context block that's supposed to reflect what the system actually knows.

### The static bundles

Six bundles are baked in at startup:

| Strand ID | Name | Predicates |
|---|---|---|
| `career` | Career | employer, job_title, working_on |
| `places` | Places | lives_in, visited |
| `relationships` | Relationships | partner |
| `projects` | Projects | working_on, building, shipped |
| `health` | Health | exercise, sleep, diet, symptom, injury |
| `creative` | Creative | writing, making, composing, hobby |

These were chosen by asking: what are the life areas where timeline continuity is most useful? Career and projects are the obvious ones. Health is included because injury and symptom atoms benefit enormously from chronological context. Places captures the movement pattern that's easy to lose in a flat atom list. Relationships is sparse but important — partner is a functional predicate where supersession chains are the entire story. Creative was included because it's a common area where people have ongoing slow-burn work that doesn't produce frequent atoms.

The registry is stored as a JSON array in `app_config` under the key `'memory.strands'`. This means user-added strands survive across restarts and can be edited without touching code.

### `strand_bootstrap()`

Called at startup as a background task. It loads the registry, checks which static bundle IDs are already present, and adds any missing ones. It never overwrites user-modified bundles and never removes anything — it's strictly additive and idempotent. Safe to call multiple times.

### `resolve_strands(atom)`

Takes an atom dict and returns a list of strand IDs that claim it. The matching is purely lexical: atom's `predicate` is lowercased and checked against each strand's `predicates` list, and atom's `subject` is checked against each strand's `subjects` list. An atom matches if either matches.

This is intentionally *not* semantic. A semantic embedder would introduce false positives in ways that are hard to audit — "injury" and "injustice" would collide. Lexical matching means the user can see exactly why an atom ended up in a strand and can correct it by editing the strand's predicate list.

The code comment is honest about this: *"The embedder is currently a lexical hashing fallback, not semantic."*

### `atoms_for_strand(strand_id, window?)`

Returns all active atoms for a strand, optionally filtered to a time window `(from_ts, to_ts)`. The window filter applies to `COALESCE(valid_from, created_at)` — it uses the atom's declared validity start if present, falling back to creation date. This makes the timeline view work correctly for atoms with explicit temporal context ("worked at Acme from 2020 to 2022") as well as for atoms without it.

The query issues separate lookups for predicate matches and subject matches, deduplicating by ID. This is slightly less elegant than a single OR query but it lets the two dimensions be extended independently when needed.

### `add_strand(name, predicates)`

Creates a user strand. The ID is derived by slugifying the name (`working_style` for "Working Style"), with integer suffixes for uniqueness. User strands have `"kind": "user"` in the registry, as opposed to `"kind": "static"` for the baked-in bundles. The distinction matters for the UI: static strands can't be deleted, user strands can.

### `propose_strand_clusters()`

This is the quarterly scan that asks: have enough novel predicates accumulated that they deserve their own strand? The algorithm:

1. Count open `insight_offer` questions — bail if 2 or more are already open (hard cap against spam)
2. Load the registry and build a set of known predicates
3. Query `memory_atom` for predicates with 3+ atoms that aren't in the known set
4. If fewer than `memory.strand_cluster_min` (default 5) novel predicates: bail
5. Build a signature hash of the first 20 novel predicates (MD5, first 12 chars)
6. Check a 30-day cooldown per signature hash in `app_config` — if recently proposed the same cluster, skip
7. Open an `insight_offer` question with the novel predicates listed in the prompt and stored in `atom_ids`

I kept the threshold at 5 predicates deliberately. A strand with fewer than 5 predicates doesn't have enough momentum to be useful — it's probably noise. The 30-day cooldown per signature prevents the same cluster from nagging every time the quarterly job runs.

The novel predicates are stored in the question's `atom_ids` field as strings (not UUIDs). This is a minor schema bend — `atom_ids` is normally atom IDs — but it lets `resolve_question` populate the new strand's predicate list when the user accepts the offer and names the strand.

### API endpoints

Three new endpoints support strand functionality:

```
GET    /api/memory/strands                  -- list all strands with atom_count + unstranded_count
PATCH  /api/memory/strands/{strand_id}      -- rename a strand (name field only)
GET    /api/memory/timeline?strand=<id>     -- strand chain view with span
```

The `GET /api/memory/strands` response includes `unstranded_count` — the number of active atoms whose predicate isn't claimed by any strand. This is surfaced in the UI as a prompt to create a new strand when the number grows large.

The timeline endpoint was already present in v2. The `strand=<id>` parameter extends it to return a strand's full atom chain instead of a single predicate chain, with a `span` field showing the date range from the oldest to newest `valid_from`.

### Frontend

In prescient mode, the Timelines tab shows a strand sidebar listing all strands with their atom counts. Selecting a strand renders a `StrandLane` component: a vertical timeline of atoms with a date filter scrubber at the top. In living mode (non-prescient), the Timelines tab shows the original `BasicChain` view grouped by predicate.

---

## P1.2 — Stale-self-image guard

### The problem it solves

Retrieval is good at finding relevant atoms but has no concept of *which version* of a fact is current. For functional predicates, only the newest atom is active — reconciliation handles that. But `self_perception` atoms and `attribute` atoms often have multiple active values at different points in time because they describe evolving properties, not binary switches. "Clay is anxious about the job market" and "Clay is optimistic about the job market" could both be active because they were true at different times. When both surface in retrieval, the model has no way to tell which one is more recent without looking at dates — and it might not bother.

The stale-self-image guard forces the issue. It annotates older atoms in the retrieved set so the model can't miss that they might be superseded.

### Implementation

`_annotate_stale_self_image(mem_rows)` runs inside `retrieve()` after the fading filter, gated to prescient tier. It:

1. Finds all `(subject, predicate)` pairs in the retrieval set where atoms have `modality='self_perception'` or `predicate_category='attribute'`
2. For each pair, queries for the newest `COALESCE(valid_from, created_at)` timestamp among active atoms with that subject+predicate
3. For any atom in the retrieved set that is NOT the newest for its pair, mutates its `text` in-place: `"{text} (as of {Mon YYYY})"`

The timestamp stamped into the annotation is the atom's *own* `valid_from` or `created_at` — not the newer atom's date. This is a subtle but important choice. Reading "Clay was anxious about the job market (as of Jan 2024)" tells the model "this was true then, there's something newer." If I stamped the newer atom's date instead, it would read "this was true until Mar 2024" — which implies the newer atom is a direct supersession, which may not be true for nuanced self-perception evolution.

The guard runs in `retrieve()`, not in `format_block()`. The reason: structured tools that receive the atom list (not just the formatted block string) also see the annotation. `format_block()` is for the chat context string; `retrieve()` is the source of truth for what the system believes.

One batch SQL query per `(subject, predicate)` pair. In practice this is at most a handful of pairs per retrieval, and the query is indexed — total cost under 1ms.

---

## P1.3 — Negative-space memory / suppression atoms

### What "negative space" means

The system proactively surfaces questions, goal checks, hypothesis proposals, and strand cluster offers. Most of the time, those are useful. But sometimes a user dismisses the same goal check repeatedly — they know it's stale but don't want to be asked about it anymore. Or they drop a goal and the system keeps proposing related hypotheses. The negative-space mechanism learns from these signals and builds a suppression model: topic areas where proactive generation should stay quiet.

### Suppression atom schema

Suppression atoms are regular `memory_atom` rows with `predicate='suppressed'` and `predicate_category='experiential'`. The `experiential` category is correct: suppression is a fact about the user's preferences for interaction, and it should never decay through the standard decay curve. Instead, suppression atoms have their own managed lifecycle via the weekly pass.

The `subject` field is the topic key — a string like `goal:Stop worrying about funding` or `Clay:job_satisfaction`. The confidence value encodes the strength of the suppression signal: 0.0 means no suppression, 1.0 means maximum suppression. The threshold for active suppression is 0.6 by default.

### `is_suppressed(topic_key, threshold=0.6)`

Single-row lookup: does an active suppression atom exist for this topic key with confidence >= threshold? Used as a fast gate before opening any proactive question or generating any hypothesis. Both `generate_hypotheses()` and `check_stale_goals()` call it before touching the question queue.

### `_upsert_suppression_atom(topic_key, ...)`

Creates a new suppression atom if none exists for the topic key, or increments the confidence of an existing one. The initial confidence for a first signal is `cap + step` (0.4 + 0.15 = 0.55 by default). Subsequent dismissals add `step` (0.15) up to `max_conf` (0.85 by default). All these are `app_config` knobs: `memory.suppress_confidence_step`, `memory.suppress_max_confidence`.

### `weekly_suppression_pass()`

Registered as `memory_suppression_pass`, runs weekly. Three phases:

**Phase 1 — Signal from dismissed questions.** Queries `memory_question` for questions with `status='dismissed'` in the past 7 days. For each, derives a topic key from the question kind and its associated atoms via `_topic_key_from_question()`. `goal_check` questions derive `goal:<atom text[:80]>`. `insight_offer` questions (strand proposals) derive `strand_proposal:<MD5 hash of prompt>`. Other questions derive `<subject>:<predicate>` from the first associated atom. Then calls `_upsert_suppression_atom()` to boost suppression for that topic.

**Phase 2 — Signal from dropped goals.** Queries for `goal_progress` events in the past 7 days where `detail.outcome == 'dropped'`. Dropped goals generate a suppression signal with key `goal:<goal text[:80]>`.

**Phase 3 — Decay pass.** Loads all active suppression atoms and applies exponential half-life decay:

```
decay = exp(−ln(2) × age_days × 86400 / half_life_s)
new_conf = old_conf × decay
```

where `age_days` is measured from `meta.last_signal_ts` (updated on every boost), falling back to `created_at`. Atoms whose decayed confidence falls below `0.4` (the `retract_floor`) are retracted via `memory.retract_atom()`. This means suppression is never permanent — if a topic key goes unmentioned for long enough, the suppression lifts and the system will start proposing it again.

The default half-life is 180 days, from `memory.suppress_half_life_days`. This is deliberately long — it should take roughly six months of silence before a dismissed topic resurfaces.

### Invariant filter in retrieval

Suppression atoms and hypothesis atoms are stripped from retrieval results by an invariant filter in `retrieve()`, applied unconditionally regardless of tier:

```python
mem_rows = {
    k: v for k, v in mem_rows.items()
    if v.get("predicate") != "suppressed"
    and v.get("modality") != "hypothesis"
}
```

Even at essential tier, if a suppression atom somehow exists, it won't appear in chat context. Internal-bookkeeping atoms have no place in the context window.

---

## P1.4 — Memory warming

### The problem

On the first message of a new session, `retrieve()` runs cold: embed the message, do the numpy KNN, run FTS, RRF merge, format block. On a large atom store that's around 100ms. For subsequent messages it's the same cost, but those feel fast because they happen after the model response starts streaming. The first message is different — the user just opened a fresh session and typed something, and they're waiting.

Warming pre-fetches the retrieval block between session creation and the first message, using a prediction of what the first message is likely to be about.

### The blend query

`_blend_query_vec(session_id, project_id)` builds a 5-component weighted query vector:

| Component | Weight | Source |
|---|---|---|
| `prev` | 0.35 | Centroid of last 10 user messages from the previous session |
| `goals` | 0.20 | Centroid of active desire/plan atoms touched in the last 14 days |
| `commits` | 0.15 | Centroid of open assistant commitment tasks |
| `slots` | 0.15 | EWMA vector for the current weekday × 4h time slot from `memory_pattern` |
| `manifest` | 0.15 | Project description embedding (only when project-scoped) |

Weights are stored in `memory.warm_weights` as JSON so they're tunable without a deploy. If a component has no data (no previous session, no open goals, no slot data), it's simply absent and the remaining weights are renormalized to sum to 1.0. The normalization happens per-call, not statically — whatever components are available contribute proportionally.

The intuition behind the weights: the previous session's content is the strongest signal about trajectory (0.35), goals and commitments describe current concerns (0.20 + 0.15), the slot pattern captures time-of-day query patterns (0.15), and the project description anchors project-scoped sessions (0.15). All are marked `[VALIDATE]` in the source — I've set reasonable priors but the right weights depend on real usage data.

The blend vector is the weighted sum of component centroids, L2-normalized.

### `warm_session(session_id, project_id)`

Called as `asyncio.create_task` from `POST /api/sessions`. Never blocks session creation. The task:

1. Checks the tier — returns immediately if `essential` (warming requires at least `living`)
2. Reads `chat.memory_block_budget` and `memory.warm_ttl_s` (default 600s in code)
3. Captures the current `memory_mutation_seq`
4. Calls `_blend_query_vec()` — if None (not enough data), returns
5. Calls `_retrieve_with_vec()` with the blend vector — vector-only, no FTS
6. Formats the block with `format_block()`
7. Evicts the oldest stash entry if the LRU cache is at capacity (32 sessions)
8. Stores the stash entry: `{block, query_vec, created_at, mutation_seq, ttl}`

The entire function is wrapped in a bare `try/except: pass`. Warming failures must never crash session creation.

### `_retrieve_with_vec()`

Warming skips FTS. The reason: FTS requires query text, and at warm time there is no query text — only a predicted vector. Vector-only retrieval over the blend vector is still a good prediction; FTS over an empty string would add nothing and could add noise. The retrieval pipeline is otherwise identical to the cold path: numpy KNN, doc vector hits, RRF, fading filter, invariant filter (suppressed/hypothesis atoms stripped), score sort, budget trim.

### `pop_warm_block(session_id, first_msg_embedding, current_mutation_seq)`

Called by `chat.py` before cold retrieval runs. Returns the pre-built block string if valid, or `None` (in which case cold retrieval runs as normal). Four checks, all must pass:

1. **Stash exists** — if no warm entry for this session, return None
2. **TTL check** — if the stash is older than its TTL, return None
3. **Mutation guard** — if `memory_mutation_seq` has changed since the stash was built, the atom set has been mutated and the cached block is stale; return None
4. **Cosine gate** — compute cosine similarity between the first message embedding and the blend query vector. If below `memory.warm_discard_cos` (default 0.30), the first message is too different from what was predicted; return None

If all four pass, return the block string and evict the stash.

The cosine gate is the interesting one. A threshold of 0.30 is deliberately permissive — it's checking for gross mismatch, not semantic equivalence. The blend vector encodes "recent trajectory," and any message within 0.30 cosine of that trajectory is probably well-served by the pre-fetched atoms. Messages below 0.30 are genuinely unexpected from the trajectory and deserve cold retrieval.

The mutation guard is a correctness safeguard. If a new atom was added between session creation and the first message (e.g. from a background job), the cached block might be missing it. The mutation guard forces cold retrieval in that case.

### Warming is latency-only

This is worth saying explicitly because it's easy to get confused. Warming is a performance optimization. It never changes what memory the user sees. If the warm block is served, the user sees exactly what cold retrieval would have computed on the same predicted query. If the warm block is discarded, cold retrieval runs and the user sees what cold retrieval computes on the actual query. The two results may differ — they're answering different queries. That's fine. The guarantee is not content-invariance with the first message; it's byte-identity to a cold computation of the predicted query at warm time.

### `update_slot_pattern(session_id, user_message)`

Called after each turn to update the `memory_pattern` table for the current time slot. The slot key is `{weekday}_{hour // 4}` — 28 possible slots (7 days × 4 blocks). The EWMA update:

```python
new_vec = 0.9 * old_vec + 0.1 * new_message_vec
new_vec = normalize(new_vec)
```

Alpha of 0.1 makes this a slow adaptation — it takes roughly 10 turns before the slot vector meaningfully shifts. That's intentional: I want the slot pattern to reflect stable habitual usage, not the last three conversations.

---

## P1.5 — Hypothesis engine v2

### What changed from v1

The v1 hypothesis engine generated predictions, stored them as atoms, and confirmed them when a matching atom arrived. The v1 confirmation was a cosine gate only — if the new atom's embedding was close enough to the hypothesis's `expected_evidence` text, the hypothesis was confirmed.

V2 makes four structural improvements:

1. **Mandatory falsifiers** — every hypothesis must include a `disconfirming_evidence` field. Hypotheses without one are dropped at generation time. A prediction without a falsifier isn't a falsifiable prediction; it's wishful thinking with extra steps.

2. **NLI testing** — instead of a cosine gate, the confirmation path runs an NLI (natural language inference) call: does the new atom *actually support* the expected evidence description? Does it refute the disconfirming evidence? This is a cheap model call but it catches cases where two texts are topically similar but semantically opposed.

3. **Flaw ledger** — per-pattern rolling precision over the last 20 outcomes. Patterns with poor precision are suppressed in the generation prompt. The system learns which of its reasoning patterns are reliably wrong.

4. **Inferred facts** — confirmed hypotheses don't just change modality; they mint a *new* atom with `modality='insight'` and archive the original hypothesis. The insight atom has an independent confidence derived from the prior, not a flat value.

### Generation

`generate_hypotheses()` is registered as `memory_hypotheses`, runs weekly. It checks the open hypothesis count against `memory.hypotheses_max_open` (default 15) — if at cap, returns early. Then:

1. Loads up to 200 recent active atoms excluding hypotheses, insights, and suppressed
2. Reads the flaw ledger from `memory.calibration` and identifies patterns below `memory.hyp_flaw_precision_floor` (default 0.40) — these are listed in the generation prompt as patterns to avoid this cycle
3. Reads suppressed topics and adds them to the generation prompt exclusions
4. Calls `llm.cheap` with `task='hypothesis_generation'` and a structured JSON format prompt

The four generation patterns are: `extrapolation`, `analogy_to_past_decision`, `goal_implication`, `correlation_promotion`. The prompt requires the model to pick one and justify it. Any item returned without `disconfirming_evidence` is silently dropped before storage. Any item with an unknown pattern is defaulted to `extrapolation`.

The `prior` from the model is clamped to `[0.05, 0.95]` and stored in `meta.prior`. Hypotheses are stored with `confidence=prior` at the atom level.

### Flaw ledger

`memory.calibration` in `app_config` stores a JSON object:

```json
{
  "hypothesis_patterns": {
    "extrapolation": { "confirmed": 4, "refuted": 2, "outcomes": ["c","c","r","c","c","r"] },
    "analogy_to_past_decision": { ... },
    ...
  },
  "last_calibration": 1234567890
}
```

`_rolling_precision(outcomes)` computes `confirmed / total` over the last 20 outcomes, where `c` = confirmed and `r` = refuted. Returns `0.5` when no data — a neutral prior that doesn't suppress anything. Patterns below the precision floor are excluded from the next generation cycle.

`_update_flaw_ledger(pattern, outcome)` appends the outcome character to the rolling window and truncates to 20. This write happens synchronously after a confirmation or refutation is committed.

I chose a rolling window of 20 rather than exponential decay. It's simple, auditable, and large enough to smooth noise while small enough to respond to genuine improvement. If the system learns better and starts getting `extrapolation` right, the window fills with `c` outcomes and suppression lifts within a few cycles.

### NLI testing: `_nli_call(atom_text, evidence_text)`

A cheap model call. The prompt asks: does the memory fact support, refute, or stay neutral toward the evidence claim? Returns `(verdict, strength)` where verdict is one of `supports`, `refutes`, `neutral` and strength is 0.0–1.0. Falls back to `('neutral', 0.5)` on any error.

The strength threshold for a confirmation is 0.6 (hardcoded as `confirm_strength_floor` in the code, `[VALIDATE]`). A verdict of `supports` with strength below 0.6 is treated as neutral — it's a weak signal, not confirmation.

### `test_hypotheses_against_atom(new_atom)`

Called from the extraction worker after every new atom insert, gated to prescient tier. Skips hypothesis, insight, and suppressed atoms (testing a hypothesis against itself or against another hypothesis would be circular).

For each open hypothesis:

1. **Horizon check** — if `meta.horizon` is past, archive the hypothesis as `hypothesis_expired` and continue. Horizon expiry is not a flaw-ledger event: running out of time is not a reasoning error.

2. **Cosine gate** — compute cosine between the new atom's embedding and both `expected_evidence` and `disconfirming_evidence` embeddings. If neither exceeds `memory.hyp_gate_cos` (default 0.50), skip this hypothesis. This avoids an NLI call for every atom against every hypothesis.

3. **NLI calls** — call `_nli_call()` against whichever evidence descriptions passed the cosine gate.

4. **Decision**: if `supports + strength >= 0.6` against expected evidence → confirm. If `supports` against disconfirming evidence OR `refutes` against expected evidence, also with strength >= 0.6 → refute. Otherwise → append observation to `meta.observations` (capped at 50).

### Confirmation: `_confirm_hypothesis(hyp, confirming_atom, prior, pattern)`

The confidence formula:

```
inferred_conf = prior × factor + base
```

where `factor` defaults to 0.8 (from `memory.hyp_confirm_conf_factor`) and `base` defaults to 0.18 (from `memory.hyp_confirm_conf_base`). Both are `[VALIDATE]`. For a median prior of 0.5: `0.5 × 0.8 + 0.18 = 0.58`. For a high-confidence prior of 0.8: `0.8 × 0.8 + 0.18 = 0.82`. The result is clamped to `[0.1, 0.98]`.

The reasoning: confirmation shouldn't simply adopt the prior as confidence. The evidence confirms the prediction, which is a meaningful update, but it doesn't make the prediction into established fact. A modest additive boost (0.18) combined with a damped prior (×0.8) produces confidence in the low-to-mid range for typical priors — high enough to surface in the Inferred tab, conservative enough to avoid displacing well-established facts in retrieval.

The confirmation mints a new atom with `modality='insight'` and archives the hypothesis. It does NOT just change the hypothesis atom's modality — a fresh atom has a fresh creation date, a fresh embedding, and a clear `meta.inferred_from_hypothesis` provenance. The hypothesis is archived (not retracted) so it remains in the audit trail.

### Refutation: `_refute_hypothesis(hyp, refuting_atom, pattern, calib_raw)`

Archives the hypothesis and updates the flaw ledger with `'r'`. No new atom is minted — a refuted hypothesis is simply closed.

### What insight atoms look like in retrieval

Insight atoms have `modality='insight'`. `format_block()` appends ` (inferred)` to their text when building the chat context string:

```python
tag = " (inferred)" if a.get("modality") == "insight" else ""
lines.append(f"- {a['text']}{tag}")
```

This means confirmed inferences are visible in chat context — unlike open hypotheses, which are never injected — but they're labeled so the model knows their epistemic status.

### Frontend

The Inferred tab (prescient mode only) has three components:

- **HypothesisCard** — open hypotheses with evidence glyphs (+/−/·), a "watched" pulse dot for hypotheses with recent observations, and a `days_left` counter until horizon
- **InferredFactCard** — confirmed inferences (insight modality) with an `(INFERRED)` badge and confidence bar
- **ScoreboardTable** — per-pattern precision stats; suppressed patterns (below precision floor) are shown with strikethrough text and italic admission text

The epistemic footer reads: *"INFERRED — SHOWN BEFORE BELIEVED"* — a reminder that these are predictions, not facts.

---

## P1.6 — Weekly diff note

### Why a note and not a notification

The weekly digest goes into the Notes surface as a regular note. The reasoning: you might want to read it now, you might want to read it later, and you might want to ignore it entirely. A note respects all three. It's also searchable and persistent. A push notification or banner is exactly the kind of interruption the memory system should avoid generating.

### Data gathering (no model call)

`generate_weekly_diff()` is registered as `memory_weekly_diff` and runs weekly. All data gathering is rule-based:

1. **New facts** — `memory_event` rows with `kind='created'` in the past 7 days, joined to `memory_atom` for confidence
2. **Notable atoms** — from the new facts, those with confidence >= 0.7, sorted descending, capped at `memory.weekly_diff_atom_cap` (default 12). Suppressed topics are filtered out
3. **Supersessions** — `memory_event` rows with `kind='superseded'` in the past 7 days, joined to get the old text; for each, the `detail.superseded_by` ID is resolved to get the new atom text. Capped at 5
4. **Questions** — counts of questions opened and resolved in the period
5. **Hypothesis events** — grouped counts of `hypothesis_confirmed`, `hypothesis_refuted`, `hypothesis_expired` from `memory_event`
6. **Compacted** — count of `retracted` events in the period

If no events at all across all six categories, the note body is just `"No memory changes this week."` and the function returns without any model call.

### Summarization and fallback

The data is assembled into a plain-text summary and passed to `llm.cheap` with `task='weekly_diff_summary'` and strict rules: factual changes only, one line per bullet, max 10 bullets, end with `"Memory actively maintained."` if changes existed. Temperature 0.1 — dry and factual.

If the model call fails for any reason, `_template_fallback()` runs instead. It's a pure Python string builder that can never fail. The template fallback produces equivalent information in a slightly more mechanical format. The user always gets a digest — there's no code path where a failed LLM call means no note.

### `upsert_diff_note(week_start_iso, title, body)`

Defined in `services/notes.py`. Idempotent by `meta={"diff_week_start": week_start_iso}` — if a diff note for this ISO week already exists, it updates the body rather than creating a duplicate. Running the job twice in the same week produces one note, not two.

### The re-ingestion guard

The note is created with `source_kind='memory_diff'`. In `workers/cowriter.py`:

```python
async def ingest_note(note_id: str):
    note = await notes.get(note_id)
    if note.get("source_kind") == "memory_diff":
        return  # never re-ingest system digest notes
```

Without this guard, the notes co-writer would extract memory atoms from the diff note itself — creating atoms about hypothesis counts and weekly totals, which is absurd. The `source_kind` check is at the point of use (the cowriter worker), not at the point of creation (`notes.create()`). That's the right place: it keeps creation generic and puts the guard where the specific concern lives.

### `register_schedule()`

Registers the weekly diff job at 7-day cadence. Paired with `workers/memory_prescient.register_schedule()` which registers the suppression pass, hypothesis generation, drift analysis, and goal stale check — all the other weekly/quarterly prescient jobs.

---

## Retrieval changes in full

Everything in `services/retrieval.py` that changed in the P1 build:

### Invariant filter (always-on, all tiers)

After the fading filter, before anything reaches the caller:

```python
mem_rows = {
    k: v for k, v in mem_rows.items()
    if v.get("predicate") != "suppressed"
    and v.get("modality") != "hypothesis"
}
```

Unconditional. Suppression and hypothesis atoms are internal bookkeeping. They must not appear in chat context regardless of tier.

### Stale guard (prescient tier only)

```python
tier_row = await db.fetchone("SELECT value FROM app_config WHERE key='memory.tier'")
if tier_row and tier_row.get("value") == "prescient":
    await _annotate_stale_self_image(mem_rows)
```

Runs after the invariant filter, before scoring. The tier check is a direct DB read rather than a `tier_allows()` call because this is an annotation pass on already-fetched data, not a gate on what gets fetched.

### Structured fields in item dicts

Every memory item dict returned by `retrieve()` now includes:

```python
"modality":           r.get("modality"),
"predicate":          r.get("predicate"),
"subject":            r.get("subject"),
"predicate_category": r.get("predicate_category"),
"valid_from":         r.get("valid_from"),
"meta":               json.loads(r["meta"]) if r.get("meta") else None,
```

These fields were always in the DB but weren't being threaded through the retrieval return value. The stale guard needs `modality` and `predicate_category` to identify candidates. The `(inferred)` tag in `format_block()` needs `modality`. Passing them in the item dict means callers don't have to make additional DB lookups.

### `(inferred)` tag in `format_block()`

```python
tag = " (inferred)" if a.get("modality") == "insight" else ""
lines.append(f"- {a['text']}{tag}")
```

Insight atoms appear in chat context labeled as inferred. The model knows that `(inferred)` items are predictions that have been confirmed by evidence, not directly observed facts. This is the epistemic hygiene principle applied to the format layer.

---

## Retrieval gating in chat (intent.py + chat.py)

Not all queries should trigger a memory lookup. "What is the capital of France?" does not need my memory. "What's my name?" does.

`memory_relevance(text)` in `services/intent.py` classifies queries:

- Returns `True` if the text matches `_MEM_WANT` patterns: explicit recall requests (`remember`, `recall`, `you know`), personal possessives (`my name`, `my project`), second-person references (`you said`, `told you`)
- Returns `False` if the text matches `_MEM_SKIP` patterns (factual lookups: `what is`, `who is`, `define`, `explain`, `how do`) AND has no personal pronouns (`I`, `my`, `me`, `we`, `our`)
- Returns `None` (ambiguous) otherwise

In `routers/chat.py`:

```python
mem_want = memory_relevance(user_text)
inject_memory = mem_want is not False or has_pinned
```

`False` skips memory injection entirely. `True` or `None` injects normally. Pinned atoms always inject regardless — they're things the user has explicitly flagged as always-relevant context.

The ambiguous `None` case injects. The asymmetry is intentional: it's better to occasionally inject memory on an irrelevant query than to miss a query where memory was genuinely needed. The false positive cost (a few extra context tokens) is lower than the false negative cost (an answer that ignores relevant personal context).

---

## Config settings endpoint

Two new endpoints in `routers/config.py`:

```
GET /api/config/settings/{key:path}   -- returns {key, value} or 404
PUT /api/config/settings/{key:path}   -- writes any app_config key
```

The `{key:path}` routing allows keys with dots (`memory.tier`). `memory.jsx` reads `memory.tier` at startup via `GET /api/config/settings/memory.tier` to know which tabs to show. The PUT endpoint is used by the tier selection flow to write `memory.tier` and `memory.tier_selected`.

These endpoints are intentionally generic — any `app_config` key is accessible. That's appropriate for a personal assistant with no multi-user concerns. If multi-tenancy were ever added, these would need scoping.

---

## Note schema changes

Two new columns added to the `note` table via migrations in `services/db.py`:

```sql
ALTER TABLE note ADD COLUMN source_kind TEXT;
ALTER TABLE note ADD COLUMN meta TEXT;
```

`services/notes.py` `create()` accepts `source_kind` and `meta` parameters. `upsert_diff_note(week_start_iso, title, body)` uses both to create idempotent weekly digest notes keyed by `meta={"diff_week_start": week_start_iso}`.

The `source_kind` column follows the same pattern as `memory_atom.source_kind`: provenance is stored at creation time and checked by consumers, keeping the guard logic at the point of use.

---

## What no longer writes to memory

Two sources that previously fed atoms into memory were removed during the P1 build:

**Notes** — `routers/notes.py` no longer enqueues `extract_memory` when a note is saved. Previously, saving a note would trigger atom extraction from its content. The problem: notes are often drafts, scratchpads, and pastes of external content. Ingesting them created noise — "Clay is considering whether to use Svelte" extracted from a note that was a copy-paste of someone else's blog post. Notes are now surfaces for writing, not sources for memory. If the user wants to convert a note's insight into memory, they can say so in chat.

**Research** — `workers/research.py` no longer pushes high-confidence findings from deep research reports into memory atoms. Research reports are about the world, not about the user. Injecting world-knowledge into the personal memory store was category confusion. If the user wants to save a research conclusion as a personal belief ("I've decided to use Postgres"), they can say so in chat and extraction handles it from there.

---

## The Memory surface — complete rewrite

`static/memory.jsx` was fully rewritten for the P1 build. The major changes:

### Tier-aware tab bar

Tabs are hidden when the user's tier doesn't include them:

| Tab | Minimum tier |
|---|---|
| Fragments | essential |
| Overview | living |
| Review | living |
| Goals | living |
| Timelines | living |
| Inferred | prescient |
| Skills | (always visible) |

The tier is loaded from `GET /api/config/settings/memory.tier` at startup and defaults to `'living'`. Essential-tier users see only Fragments and Skills — the other tabs require background jobs that don't run at essential tier.

### Overview tab (living+)

Summary cards showing: recent activity count, open review question badge, goals count, and (in prescient mode) inferred fact count. Each card taps through to the relevant tab. The goal is a dashboard that answers "what has the memory system done lately?" without digging into individual tabs.

### Fragments tab

The original Memory Garden view, extended with:
- Subject-grouped `SubjectBed` components (atoms grouped by `subject` field)
- Category filter pills (filter by `predicate_category`)
- Faded toggle (show/hide atoms below the fading threshold)

### Review tab

`QuestionCard` components now support `insight_offer` kind in addition to `conflict` and `goal_check`. The `accept_named` resolution type — used for strand cluster offers where the user names the new strand — shows an inline text field.

### Goals tab

Desire and plan atoms with modality color bars. Goal closure (achieved/dropped) is handled from here.

### Timelines tab

Living mode shows the original `BasicChain` vertical list per predicate. Prescient mode shows the strand sidebar + `StrandLane` per selected strand with a date filter scrubber.

### Inferred tab (prescient only)

Three components: `HypothesisCard`, `InferredFactCard`, `ScoreboardTable`. The epistemic footer — *"INFERRED — SHOWN BEFORE BELIEVED"* — is displayed at the bottom of the tab.

---

## Seeding

`seed_memory.py` at the project root is a one-shot script that populates the memory store with approximately 20 sample atoms covering:

- Identity (name, location, timezone)
- Career (employer, job title, current work)
- Atelier project work (what's being built, recent shipped features)
- Goals (near-term and longer-horizon desires)
- Working style preferences
- Two sample hypotheses (open, with both `expected_evidence` and `disconfirming_evidence` populated)
- One sample insight atom (a confirmed inference)

It also sets `memory.tier=prescient` and `memory.tier_selected=true` so the full prescient tab set is visible immediately.

All atoms are written with `dedup=True` — running the script twice won't create duplicates.

```bash
python seed_memory.py
```

---

## What I didn't build in P1

**Semantic strand clustering** — the `strand_cluster` LLM task is registered and `propose_strand_clusters()` is wired into the quarterly drift job, but the current clustering is purely lexical. Semantic clustering would catch cases like `reading` and `studying` going into the same strand, but it also introduces false positives that are hard to explain to the user. Lexical is conservative and auditable; semantic is the natural next step once real usage data accumulates.

**Suppression UI** — there's no surface for viewing or directly editing suppression atoms. They're managed entirely by the weekly pass based on dismiss signals. Adding a "mute this topic" button to the Review tab would be straightforward but wasn't necessary for the core behavior.

**Warming for non-session chat** — warming only fires from `POST /api/sessions`. In-session continuation (follow-up messages) doesn't have a warming equivalent. The second-and-later messages are already preceded by streaming output, so the ~100ms retrieval cost is hidden by the time-to-first-token.

**Hypothesis confidence calibration** — the flaw ledger tracks per-pattern precision but doesn't adjust the generation prompt's prior range based on historical calibration. If `extrapolation` is reliably under-confident, the system doesn't compensate by instructing the model to nudge priors up. This would be useful but requires enough outcome data to be meaningful.

**Strand auto-assignment notification** — when you create a new strand via `accept_named`, atoms with matching predicates automatically appear in its timeline on next query. But there's no notification that new atoms joined a strand after creation — you discover it by looking at the strand lane.
