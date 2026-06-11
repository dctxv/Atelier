# Prescient Memory — Part 1

*Six new capabilities layered on top of Living Memory v2: strand timelines, stale-self-image annotation, negative-space suppression, session warming, a richer hypothesis engine, and a weekly digest. Written by Clay.*

---

## What this adds

Living Memory v2 was the foundation: structured atoms, decay, reconciliation, the uncertainty register. Part 1 is the first layer of *reasoning forward* — the system not just recording and correcting, but noticing patterns, suppressing what you've moved past, pre-loading what you'll probably ask about, and writing a weekly note about what changed.

The capabilities are split into two tiers. `living` is the default; it gets strands, the stale guard, suppression, and warming. `prescient` adds the full hypothesis engine and the weekly diff. The gate is `tier_allows(capability)` in `services/config.py`.

---

## P1.0 — The capability gate

Two tier keys live in `app_config`:

- `memory.depth` — `"basic"`, `"reflective"`, or `"prescient"`. Original v2 key controlling which background extraction jobs run (see [memory-tier-selection.md](memory-tier-selection.md)).
- `memory.tier` — `"essential"`, `"living"`, or `"prescient"`. The Part 1 capability gate. Controls which P1+ features are active. Default: `"living"`.

These are orthogonal. `memory.depth` gates the original weekly jobs; `memory.tier` gates the new P1 features.

`services/config.py` implements the gate:

```python
_TIER_ORDER = {"essential": 0, "living": 1, "prescient": 2}
_CAP_TIER = {
    "strands":             "living",
    "stale_guard":         "living",
    "suppression":         "living",
    "warming":             "living",
    "hypothesis_nli":      "prescient",
    "weekly_diff":         "prescient",
    "strand_cluster":      "prescient",
    ...
}

async def tier_allows(capability: str) -> bool:
    current = (await get_setting("memory.tier") or "living").strip().lower()
    required = _CAP_TIER.get(capability, "living")
    return _TIER_ORDER.get(current, 1) >= _TIER_ORDER.get(required, 1)
```

Four new task tiers were added to `services/llm.py` — all mapped to `"cheap"` since they run in background jobs and cost is cumulative:

| Task tier | Used by |
|---|---|
| `strand_cluster` | Cluster proposal prompt |
| `hypothesis_generation` | Hypothesis generation prompt |
| `hypothesis_nli` | NLI entailment call |
| `weekly_diff_summary` | Weekly digest summarization |

---

## P1.1 — Strand timelines

### What strands are

A strand is a named bundle of predicates and subjects that aggregates related memory atoms into a life-area timeline. "Career" owns the `employer`, `job_title`, and `working_on` predicates. "Health" owns `exercise`, `sleep`, `diet`, `symptom`, `injury`. An atom can belong to multiple strands — a project atom with `predicate='working_on'` belongs to both Career and Projects.

Strands are a UI concept. They don't affect how atoms are stored, extracted, or injected into chat. They're a lens on existing data.

### The registry

Six static bundles ship with the app:

| Strand | Predicates |
|---|---|
| career | employer, job_title, working_on |
| places | lives_in, visited |
| relationships | partner |
| projects | working_on, building, shipped |
| health | exercise, sleep, diet, symptom, injury |
| creative | writing, making, composing, hobby |

These live in `app_config` under the key `memory.strands` as a JSON array. `strand_bootstrap()` in `services/strands.py` checks for each static bundle on startup and inserts any missing ones — it's idempotent, so every startup is safe. It runs as `asyncio.create_task` in the app lifespan so it doesn't block startup.

Users can add their own strands. `add_strand(name, predicates)` slugifies the name, ensures uniqueness, and appends to the registry. The slug becomes the strand's ID — "Book Club" becomes `book_club`, with a suffix appended if that ID is already taken.

### Membership resolution

`resolve_strands(atom)` takes an atom and returns the list of strand IDs it belongs to. The match is lexical — case-folded predicate and subject values checked against each strand's predicate and subject lists. This is conservative by design: no embeddings, no fuzzy matching. A novel predicate like `reading_group` won't automatically land in the `creative` strand unless you add it. The cluster proposal (below) is how novel predicates get discovered.

### Cluster proposal

`propose_strand_clusters()` runs quarterly (triggered from drift analysis). It finds predicates with at least three active atoms that don't appear in any existing strand. If there are five or more such predicates, it opens an `insight_offer` question in the uncertainty register: *"You have N memory predicates that don't fit existing life-area timelines: X, Y, Z. Consider grouping some into a new timeline."*

The novel predicates are stored in the question's `atom_ids` field (reusing the field for non-UUID string values — they won't resolve to atoms so the list appears empty in the review card, but `resolve_question` can read them back). A 30-day cooldown per predicate-set hash prevents the same question from reopening immediately.

When the user responds with `accept_named` and types a name, `resolve_question` calls `add_strand(detail, atom_ids)` — the typed name becomes the strand's display name, and the novel predicates become its initial predicate list.

### New endpoints

```
GET  /api/memory/strands                 → { strands: [...], unstranded_count: N }
PATCH /api/memory/strands/{strand_id}   → rename a strand
GET  /api/memory/timeline?strand=<id>   → { strand, name, chains, span: {from, to} }
```

The strand timeline endpoint builds a chain per predicate × subject combination in the strand and returns all of them together with the overall time span.

### Frontend

The Timelines tab adapts to tier:
- **Living**: `BasicChain` — a vertical list of supersession chains, one per predicate, like the v2 timeline view.
- **Prescient**: a strand sidebar on the left lets you pick a strand; the main area shows `StrandLane` — a horizontal timeline with atoms plotted by date and a date-range scrubber to zoom into a period.

---

## P1.2 — Stale-self-image guard

### The problem

Retrieval returns the most relevant atoms, which might include both a current belief ("I work in AI") and a stale one ("I work in fintech"). The stale atom might score highly because the conversation is about fintech. Without any annotation, the model can't tell that the fintech belief was superseded and may treat it as current fact.

### The solution

`_annotate_stale_self_image(mem_rows)` runs inside `retrieve()` after the fading filter, gated to `living` tier:

1. Collect all (subject, predicate) pairs from atoms where `modality='self_perception'` or `predicate_category='attribute'`.
2. For each pair, find the timestamp of the most recent atom in the full database (not just the retrieval window).
3. Any atom whose own timestamp is *not* the most recent gets its text mutated in-place: `"{text} (as of {Mon YYYY})"`.

The timestamp used is the atom's own `valid_from` or `created_at` — not the newer atom's date. This is intentional. The annotation says "this was asserted to be true in March 2024", not "this was superseded in August 2025". A model reading "I work in fintech (as of Mar 2024)" understands the staleness without needing to know when the replacement appeared.

The guard runs in `retrieve()`, not in `format_block()`. This means anything consuming the structured retrieval result — not just the chat block — sees the annotation.

---

## P1.3 — Negative-space memory

### What it is

Suppression atoms track topics you've moved past or explicitly dismissed. They're the memory system's way of saying "don't keep bringing this up." A suppression atom has `predicate='suppressed'`, `predicate_category='experiential'` (so it never decays by the standard curve), and a confidence value that represents how strongly the topic should be suppressed.

### Creation and decay

`is_suppressed(topic_key, threshold=0.6)` checks whether a topic has a suppression atom above the threshold. `_upsert_suppression_atom(topic_key, confidence)` creates or updates it.

`weekly_suppression_pass()` runs as a registered job (`memory_suppression_pass`, weekly):

1. **Boost**: for every dismissed review question, boost the suppression confidence for that topic by 0.2 (capped at 0.95).
2. **Decay**: apply exponential half-life decay to all active suppression atoms. The half-life is `memory.suppress_halflife_days` (default 180). `decay = exp(-ln(2) × age_days / halflife)`.
3. **Retract**: any suppression atom whose decayed confidence falls below 0.4 is retracted — the topic is no longer suppressed, and the system can surface it again.

### Where suppression gates things

Three places check `is_suppressed()` before acting:

- **Goal staleness check** — won't open a "still planning to?" question for a suppressed goal.
- **Hypothesis generation** — suppressed topics are listed in the flaw ledger section of the generation prompt so the model doesn't propose hypotheses about them.
- **Weekly diff** — suppressed topics are filtered from the notable facts list before summarization.

### Chat context exclusion

The invariant filter in `retrieve()` strips suppression and hypothesis atoms before any retrieval results leave the function:

```python
mem_rows = {k: v for k, v in mem_rows.items()
            if v.get("predicate") != "suppressed"
            and v.get("modality") != "hypothesis"}
```

This is enforced at the retrieval layer, not at the prompt-building layer, so suppressed and hypothesis atoms never reach chat context regardless of how the caller uses the results.

---

## P1.4 — Memory warming

### Why

The first message in a new session pays the full retrieval cost: KNN matrix lookup, FTS search, RRF merge, format pass. On a large atom store that's 100ms+. Warming moves this work to session creation time — before the user types anything — so the first message's retrieval block is already built.

### How

`warm_session(session_id, project_id)` is called as `asyncio.create_task` from `POST /api/sessions`. It never blocks the session creation response.

It builds a **blend query vector** from five components:

| Component | Weight | Source |
|---|---|---|
| Previous session's last message | 0.35 | Last user message embedding in the most recent session |
| Goals / desires | 0.20 | Mean embedding of active desire/plan atoms |
| Commitments | 0.15 | Mean embedding of open commitment tasks |
| Slot pattern | 0.15 | EWMA query vector for this session from `memory_pattern` |
| Manifest / profile | 0.15 | Mean embedding of high-salience pinned atoms |

If a component is missing (no prior session, no goals, etc.), its weight is redistributed proportionally to the remaining components. The blend vector is renormalized before use.

The warming path runs `_retrieve_with_vec()` — retrieval using the pre-computed vector directly, skipping FTS (FTS needs actual query text). The result is serialized and stored in `_stash`, a module-level `OrderedDict` capped at 32 entries (LRU eviction on insert when full).

### Serving the warm block

`pop_warm_block(session_id, first_msg_embedding, current_mutation_seq)` is called at the start of the first chat turn:

1. **TTL check**: stash entry must be within `memory.warm_ttl_s` seconds of creation (default 3600). Expired entries are evicted.
2. **Mutation check**: `memory_mutation_seq` in `app_config` must match the value at warm time. Any memory write since warming invalidates the stash.
3. **Cosine gate**: cosine similarity between the first message embedding and the blend vector must be ≥ `memory.warm_discard_cos` (default 0.30). A low similarity means the first message is too different from what was predicted to trust the pre-built block.

If all three pass, the warm block is returned and the stash entry is evicted. Otherwise, `None` is returned and the caller runs cold retrieval normally.

The guarantee is **byte-identity to a cold computation of the predicted query at warm time** — not content-invariance with the exact first message. Warming is a latency optimization. Correctness never depends on it.

### Slot pattern EWMA

`update_slot_pattern(session_id, user_message)` updates a per-session query vector in `memory_pattern` using EWMA (α=0.1):

```
new_vec = (1 − α) × old_vec + α × message_embedding
```

This gives each session a slowly-adapting trajectory of what topics it tends to ask about, used as the slot-pattern component in future blend vectors.

---

## P1.5 — Hypothesis engine v2

### What changed from v1

V1 hypotheses were generated and confirmed but the engine had no disconfirming-evidence requirement, no NLI testing, and no flaw ledger. V2 fixes all three.

### Generation

The generation prompt now requires `disconfirming_evidence` for every hypothesis. Any hypothesis the model proposes without a plausible disconfirmation is dropped before storage. This is a hard filter, not a score — a hypothesis that can't be falsified in principle isn't useful.

The flaw ledger (`memory.calibration` in `app_config`) tracks a rolling 20-outcome list per generation pattern:

| Pattern | Meaning |
|---|---|
| `extrapolation` | Current trend continues |
| `analogy_to_past_decision` | You behaved this way before in similar circumstances |
| `goal_implication` | This goal logically implies that action |
| `correlation_promotion` | Two things keep occurring together |

Patterns with precision below the floor (`memory.hyp_flaw_precision_floor`, default 0.40) are listed in the generation prompt so the model generates fewer hypotheses of that type. This is the calibration loop: bad patterns get suppressed, good patterns keep running.

### NLI testing

Every new atom inserted by the extraction worker (gated to prescient tier, not a hypothesis/insight/suppressed atom) triggers `test_hypotheses_against_atom(new_atom)`:

1. Cosine similarity between the new atom and each open hypothesis's `supporting_evidence` text. Below 0.25: skip.
2. `_nli_call(atom_text, evidence_text)` — cheap model prompt asking whether atom_text confirms, refutes, or is neutral to evidence_text. Returns `(verdict, strength)`.
3. The call runs against *both* supporting and disconfirming evidence descriptions.

**On confirmation**: `_confirm_hypothesis()` mints a *new* insight atom (`modality='insight'`, `confidence = prior × 0.8 + 0.18`). It does not mutate the original hypothesis atom — that stays in the archive as the provenance record. The formula is marked `[VALIDATE]` — it's conservative enough that confirmed hypotheses don't land at full certainty, but high enough to be useful in retrieval.

**On refutation**: `_refute_hypothesis()` archives the hypothesis and updates the flaw ledger.

**On neutral**: appends an observation to `meta.observations` — the hypothesis stays open but gains a record of the evidence that wasn't strong enough to resolve it.

### Frontend (Inferred tab, prescient only)

- **HypothesisCard**: shows `supporting_evidence` and `disconfirming_evidence` with `+` / `−` / `·` glyphs. A pulse dot appears if `meta.watched=True`. `days_left` counter counts down from `valid_until`. Confirm / Reject / Watch buttons.
- **InferredFactCard**: shows insight atoms (confirmed hypotheses) with an `(INFERRED)` badge. Confirm locks confidence to 0.98; Reject retracts.
- **ScoreboardTable**: one row per generation pattern. Precision shown as percentage. Patterns below the floor have strikethrough text and an italic admission: "generating fewer of these".
- **Epistemic footer**: `INFERRED — SHOWN BEFORE BELIEVED`. This is deliberate. Confirmed hypotheses appear in the Inferred tab before the user has manually verified them. The footer makes the epistemics visible.

---

## P1.6 — Weekly diff note

### Why a note and not a notification

The weekly digest goes into the Notes surface as a regular note, not a push notification or a banner. The reasoning: you might want to read it now, you might want to read it later, and you might want to ignore it entirely. A note respects all three. It also means it's searchable and persistent.

### What it contains

`generate_weekly_diff()` gathers data without any model calls:

- Facts recorded: count of `created` events in the past 7 days.
- Notable new facts: atoms with `confidence >= 0.7`, sorted descending, capped at `memory.weekly_diff_atom_cap` (default 12). Suppressed topics filtered out.
- Updates: old→new text pairs from `superseded` events, joined to get the new atom's text. Up to 3 shown.
- Review activity: questions opened and resolved this week.
- Hypothesis events: confirmed, refuted, expired — by kind.
- Stale facts removed: count of `retracted` events.

If the week had no events, the note body is just "No memory changes this week." No model call.

Otherwise, the data is summarized by the cheap model (task `weekly_diff_summary`) with strict rules: factual changes only, one line per bullet, "Memory actively maintained." footer if anything changed. If the model call fails, `_template_fallback()` renders the same data as plain markdown without any model dependency.

### Idempotency

`upsert_diff_note(week_start_iso, title, body)` in `services/notes.py` looks for an existing note where `source_kind='memory_diff'` and `meta={"diff_week_start": week_start_iso}`. If found, it updates the body and title. If not, it creates a new note. Running the job twice in the same week produces one note, not two.

The note's `source_kind='memory_diff'` is the guard against re-ingestion. `workers/cowriter.py` returns early if a note has this source kind — so the digest never creates memory atoms about the memory system.

---

## Retrieval changes

### Structured fields in retrieve() output

Every item returned by `retrieve()` now includes the full set of structured fields:

```python
{
    "id": ..., "text": ..., "score": ...,
    "modality": ..., "predicate": ..., "subject": ...,
    "predicate_category": ..., "valid_from": ...,
    "meta": ...,   # JSON-parsed dict, or None
}
```

This lets callers (chat, warming, timelines) use the structured data without a second DB lookup.

### format_block() tagging

`format_block()` appends ` (inferred)` to any atom with `modality='insight'`. This makes it visible in the chat context block that a particular belief was inferred, not directly stated. The model can calibrate its confidence accordingly.

---

## Retrieval gating

Not every chat message needs memory. "What is the capital of France?" has nothing to do with personal facts, and injecting a memory block into that context wastes tokens and can confuse the model.

`memory_relevance(text)` in `services/intent.py` gates injection:

- Returns `True` if the message matches `_MEM_WANT` patterns: explicit recall requests ("remember", "recall", "you know"), personal possessives ("my name", "my project"), or second-person references ("you said", "you know").
- Returns `False` if the message matches `_MEM_SKIP` patterns (factual lookups: "what is", "who is", "define", "explain", "how do") *and* contains no personal pronouns.
- Returns `None` (ambiguous) otherwise.

In `routers/chat.py`:

```python
mem_want = memory_relevance(user_text)
inject_memory = mem_want is not False or has_pinned
```

`False` skips memory injection. `True` or `None` injects normally. Pinned atoms always inject regardless — they're things you've explicitly flagged as always-relevant context.

---

## Config settings endpoint

`GET /api/config/settings/{key:path}` — returns `{"key": ..., "value": ...}` for any `app_config` key, or 404 if not set.

`PUT /api/config/settings/{key:path}` — writes any key. No whitelist — caller must be authenticated.

The Memory surface uses this to load `memory.tier` at startup so it knows which tabs to show. Previously there was no generic settings read endpoint; callers either used the `/api/config` aggregate response or read through specific typed endpoints.

---

## Note schema changes

Two columns were added to the `note` table via the migration system:

```sql
ALTER TABLE note ADD COLUMN source_kind TEXT
ALTER TABLE note ADD COLUMN meta        TEXT
```

`notes.create()` accepts `source_kind` and `meta` kwargs. `upsert_diff_note()` uses both to maintain idempotency: it queries `WHERE source_kind='memory_diff' AND meta=?` with the JSON-serialized week key.

---

## What no longer writes to memory

**Notes**: the `ingest_note` enqueue was removed from `routers/notes.py`. Notes are personal writing — they're searchable through the note index, but saving a note no longer creates memory atoms. Memory is for facts the system extracts from *conversation*, not documents.

**Research**: the high-confidence findings push was removed from `workers/research.py`. Research reports stay in the research surface; they don't flow into the atom store. The personal context lookup at the start of a research run still works (retrieval reads existing atoms); it just no longer writes back.

---

## Full new endpoint list

```
GET  /api/memory/strands                     -- list strands with atom counts
PATCH /api/memory/strands/{strand_id}        -- rename a strand
GET  /api/memory/timeline?strand=<id>        -- strand lane with span
GET  /api/memory/inferred                    -- hypotheses, inferred facts, scoreboard
POST /api/memory/inferred/{id}/confirm       -- confirm (confidence=0.98, modality=factual)
POST /api/memory/inferred/{id}/reject        -- reject (retract + update flaw ledger)
POST /api/memory/inferred/{id}/watch         -- set meta.watched=True
GET  /api/config/settings/{key}              -- read any app_config key
PUT  /api/config/settings/{key}              -- write any app_config key
```

---

## Seeding sample data

`seed_memory.py` at the project root populates ~20 structured atoms covering identity, career, Atelier project work, goals, working style preferences, two hypotheses, and one inferred fact. It also sets `memory.tier=prescient` and `memory.tier_selected=true`.

Run once after first app startup:

```bash
python seed_memory.py
```

Safe to re-run — `dedup=True` on all atoms means nothing doubles up.

---

## What's still deferred

**Strand membership editing** — the UI shows which strand an atom belongs to, but there's no drag-to-add or remove-from-strand interaction. Membership is purely computed from predicates and subjects.

**Cross-strand atom view** — an atom belonging to both Career and Projects appears in both strand lanes independently. There's no "show me atoms that appear in multiple strands" view.

**Warming for mobile / long-idle sessions** — the TTL is 1 hour. Longer-idle sessions always fall back to cold retrieval. A persistent warm stash (backed by the DB rather than in-process memory) would survive restarts and long idle periods.

**Manual hypothesis entry** — you can confirm or reject hypotheses the system generates, but you can't write your own. The Inferred tab is currently read-only for manual entry.

**Strand auto-assignment** — when you create a new strand via `accept_named`, its predicates are seeded from the novel predicates that triggered the question. But atoms with predicates *added later* to the strand don't retroactively appear in its timeline until the timeline endpoint is queried (it's always computed from current predicate membership, so they will appear — but there's no notification that new atoms joined a strand).
