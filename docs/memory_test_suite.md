# Memory System — Comprehensive Evaluation Suite

A rigorous, repeatable battery for grading Atelier's Living/Prescient Memory.
Designed to test not just "does it store facts" but the full capability ladder
up to **detecting behavioural patterns the user cannot see in themselves**.

> Source data of record for these tests: the "Clay" vault synthesis. Where a
> case cites Clay, the expected extraction is derived from that document.

---

## 0. How to run this (and why the first run failed)

### The gate you must not accidentally defeat

Extraction is **two-gated** before any model call:

1. **Hot-path gate** (`routers/chat.py`): enqueue if `len(user_text) >= 20` OR
   `_significance_score > 0`. Almost everything passes this.
2. **Worker significance gate** (`workers/extraction.py:_significance_score`):
   a rule-based score in `[0,1]`.
   - `score < 0.3` → **hard skip, no model call**
   - `0.3 ≤ score < 0.7` → cheap model yes/no
   - `score ≥ 0.7` → extract

`_significance_score` is **dominated by first-person pronoun density** (`I, my,
me, I'm, I've, I want, I prefer…`) plus length and preference words. It carries
a **code penalty** for ``` ``` ``` fences / `def`/`class`/`import`.

**Consequence:** clinical, third-person, bullet-point note fragments score
0.24–0.57 and get dropped or coin-flipped. A test that feeds note fragments
measures the *tester's phrasing*, not the memory system.

### Mandatory input rules for every test below

- **First person, natural prose.** "I prefer small groups" — not
  "Small group preference (max 4)".
- **One disclosure cluster per turn**, 3–6 sentences. Mixing 8 topics into one
  bullet dump destroys per-turn attribution.
- **Wait for the background job**, then poll. Extraction is async; the UI polls
  `/api/memory` every 6s. Allow ~10s after each turn before reading.
- **Use `source_kind="chat"`.** Only chat turns are extracted (see §13).
- **Set tier to `prescient`** for §11–§12 (behavioural inference). Living tier
  will never produce hypotheses.

### Scoring

For each case record: **Captured / Missing / Misfired / Miscategorised**, and
for captured atoms verify the full shape: `subject · predicate · object ·
modality · predicate_category · confidence · salience`.

A pass = correct presence/absence **and** correct shape. Right fact, wrong
modality is a **partial** (△), not a pass.

---

## 1. Extraction Fundamentals — does first-person disclosure land at all

| ID | Input (paste as chat) | Expect stored | subject·predicate·object | modality | category |
|----|----|----|----|----|----|
| F1 | "I work as a freelance software developer, mostly Python and TypeScript." | yes ×2–3 | user·job_title·freelance software developer; user·skill·Python; user·skill·TypeScript | factual | functional / multi_valued |
| F2 | "I'm vegetarian and I have been for about three years." | yes | user·diet·vegetarian | factual | functional |
| F3 | "I live in London now — moved here from Dublin two years ago." | yes ×2 | user·lives_in·London; user·lived_in·Dublin | factual | functional / experiential |
| F4 | "I prefer small groups, honestly four people max when I go out." | yes | user·social_preference·small groups | opinion | attribute |
| F5 | "Physical touch is my primary love language." | yes | user·love_language·physical touch | self_perception | functional |

**Pass bar:** ≥ 90% of F-cases stored. This is the floor; if F-cases fail, the
endpoint/model wiring is broken, not the logic.

---

## 2. Modality Discrimination — the 7-way split

The extractor emits one of: `factual | opinion | desire | plan |
self_perception | hypothetical | commitment`. Each must be distinguished.

| ID | Input | Correct modality | Trap it rules out |
|----|----|----|----|
| M1 | "I use Cursor as my editor." | factual | not opinion |
| M2 | "I actually prefer Cursor over VS Code now." | opinion (comparative) | not bare factual |
| M3 | "I want to move to a four-day work week eventually." | desire | not plan (no commitment/date) |
| M4 | "I'm switching to a four-day week starting next month." | plan | not desire (has intent+time) |
| M5 | "I think I'm someone who stays one level above his feelings." | self_perception | not factual, not opinion-about-world |
| M6 | "If I ever moved back to Dublin I'd probably go freelance again." | hypothetical | conf ≤ 0.60 |
| M7 | "I'll text you the address at 9pm." | commitment | routes to task table (§14) |

**Confidence caps to verify** (`workers/extraction.py` + `services/memory.py`):
factual ≤ 0.95, plan ≤ 0.85, desire ≤ 0.80, hypothetical ≤ 0.60.

> **Known consistency bug to flag:** the extractor emits `self_perception` and
> `opinion`, and `hypothetical`. But the graph UI (`static/memory.jsx
> MODALITY_SHAPE/COLORS`) only knows `factual/desire/plan/commitment/hypothesis/
> insight`. So `self_perception` (the dominant Clay modality) and `opinion`
> render as undifferentiated dots, and `hypothetical` never matches `hypothesis`.
> A top-tier system must reconcile these enums end-to-end.

---

## 3. Predicate Category — drives reconciliation behaviour

| ID | Input | category | Why it matters |
|----|----|----|----|
| C1 | "My employer is Acme." then later "I work at Globex now." | functional | second **supersedes** first |
| C2 | "I like coffee." then "I like tea." | multi_valued | both coexist, no supersession |
| C3 | "My favourite language is Python." then "My favourite is Rust now." | comparative | new supersedes old |
| C4 | "I visited Tokyo." then "I visited Berlin." | experiential | accumulate, never conflict |
| C5 | "I'm fairly introverted." then "I've gotten more outgoing this year." | attribute | evolving trait, time-ranged |

**Pass bar:** category correct AND the reconciliation in §6 behaves accordingly.

---

## 4. Polarity & Intensity — sentiment fidelity

| ID | Input | polarity | intensity | Note |
|----|----|----|----|----|
| P1 | "I like my job." | +, ~0.4–0.6 | moderate | baseline positive |
| P2 | "I love my job." | + (same sign as P1) | high | same polarity, higher intensity |
| P3 | "I can't stand open-plan offices." | strong − | high | negative captured, not dropped |
| P4 | "I'm excited but honestly kind of scared about the move." | TWO atoms | — | layered emotion → split polarities (rule 5) |

**Pass bar:** P2 intensity > P1 with equal polarity sign; P4 yields two opinion
atoms, not one muddied one.

---

## 5. Negation Traps — must never invert to a positive

| ID | Input | Correct outcome | Failure mode to catch |
|----|----|----|----|
| N1 | "I don't drink alcohol." | negative-polarity fact OR retraction; never "drinks alcohol" | bare positive |
| N2 | "I no longer work at Acme." | retraction/supersession of employer·Acme | leaves stale atom active |
| N3 | "It's not that I dislike her — I just need space." | no spurious "dislikes her" atom | naive keyword "dislike" |

---

## 6. Reconciliation — supersession / corroboration / retraction

Run these as **ordered pairs across separate turns** (wait between).

| ID | Turn A | Turn B | Expected DB transition |
|----|----|----|----|
| R1 | "I work at Acme." | "I just started at Globex." | A → status `superseded`, `superseded_by` = B; B active (functional) |
| R2 | "I live in London." | "I live in London." (restated) | B skipped; A `salience`/confidence **corroborated** upward, no dup |
| R3 | "My favourite editor is VS Code." | "Cursor is my favourite editor now." | A superseded by B (comparative) |
| R4 | "I'm vegetarian." | "Actually I eat fish now, I'm pescatarian." | A retracted/superseded; B active; correction recognised |
| R5 | "I visited Tokyo in 2019." | "I visited Tokyo again in 2023." | BOTH active (experiential never conflicts) |

**Verify in `/api/memory/{id}/events`:** `superseded`, `corroborated`,
`retracted` events are logged with correct detail.

---

## 7. Temporal Resolution

| ID | Input | `temporal_raw` | Resolved? |
|----|----|----|----|
| T1 | "I moved to London two years ago." | "two years ago" | valid_from ≈ now − 2y |
| T2 | "I returned to church on Good Friday 2026." | "Good Friday 2026" | concrete date anchored |
| T3 | "I quit smoking last March." | "last March" | resolved against current date in prompt |

**Pass bar:** `temporal_raw` preserved verbatim AND a plausible `valid_from`
set. (Current date is injected into the extract prompt — verify it's used.)

---

## 8. Third-Party Handling & Confidence Dampening

| ID | Input | subject | confidence rule |
|----|----|----|----|
| TP1 | "My sister Aoife is studying medicine in Cork." | aoife | ×0.8 dampening (≤ ~0.72) |
| TP2 | "Marcus told me Mary thought I was egoistic." | marcus / mary | dampened; sensitive third-party claim |
| TP3 | "My mum goes quiet during conflict." | mum (Clay) | third-party trait, dampened |

**Pass bar:** subject ≠ `user`; confidence visibly reduced vs a first-person
equivalent.

---

## 9. Non-Literal Language — sarcasm, hyperbole, idiom

| ID | Input | Correct outcome |
|----|----|----|
| NL1 | "Oh I just *love* being on call at 3am." (sarcasm) | confidence ≤ 0.3, `meta.non_literal=true`, NOT a positive "loves on-call" |
| NL2 | "I've told him a million times to stop." | no quantity atom extracted (hyperbole) |
| NL3 | "I'm dying to see the new release." | desire, not a literal health fact |

---

## 10. Multi-Fact Density & Salience Grading

| ID | Input | Expect |
|----|----|----|
| D1 | "I'm 24, living in London, freelance dev, vegetarian, and I'm building a project called Atelier that's my main focus." | 5 distinct atoms, correct subjects/predicates each |
| D2 | (same turn) | "main focus / most focused on" → highest `salience`; incidental facts lower |
| D3 | "I had toast for breakfast." | low salience or not stored (ephemeral, not durable) |

**Pass bar:** salience ordering reflects stated importance; ephemeral trivia
(D3) does not pollute memory.

---

## 11. Behavioural Inference — the prescient tier (set tier=prescient)

This is the headline capability: **surfacing patterns the user never stated
outright.** These do NOT come from single-turn extraction — they require the
hypothesis engine (`workers/memory_prescient.py`), which runs weekly and tests
hypotheses against incoming atoms. To test deterministically, you may invoke
`generate_hypotheses` / `test_hypotheses_against_atom` directly, or seed several
turns and trigger the weekly job.

Generation patterns the engine is allowed to use: `extrapolation,
analogy_to_past_decision, goal_implication, correlation_promotion`.

| ID | Seed turns (first person, separate) | Pattern the system should INFER | Generation pattern |
|----|----|----|----|
| B1 | Turn: "I keep explaining away when she replies slowly." + later "I told myself Valerie was just busy." + later "I did the same thing with May at first." | **Excuse-making loop is romantic-domain-specific** — never appears with friends/colleagues | correlation_promotion |
| B2 | "Things only feel resolved once they're actually over." + "The waiting is worse than the ending." | **Detachment dependency** — relief at endings, distress in the unresolved middle | extrapolation |
| B3 | "I was surprised Marcus still wanted to be close after I opened up." + "Same with Livia." | **Relational-impermanence belief still operating** — surprise at retained closeness as the tell | analogy_to_past_decision |
| B4 | "Rest feels lazy when it's just for me." + "I only relax once I've earned it with output." | **Productivity = worth scorecard**, unintegrated despite stated theology | goal_implication |
| B5 | "I get close, then I get confused about what we are, then I pull back." (stated once, plainly) | **Distancing-when-close triggered by category ambiguity, not feelings** | extrapolation |
| B6 | "My bank balance dropped under $300 and I spiralled." (once) | **Specific financial trigger threshold (~$300)** as anxiety cue | correlation_promotion |

**Pass bar (the high one):** the engine forms a hypothesis with a stated
`prior`, `expected_evidence`, `disconfirming_evidence`, and a horizon; the
hypothesis is shown in the **Inferred** tab *before* it is believed (the
"shown before believed" law); and it is NOT injected into chat context until
confirmed. Verify via `GET /api/memory/inferred`.

**Anti-overreach bar:** the engine must NOT fabricate clinical claims (e.g.
"user has attachment disorder"). Hypotheses must be behavioural and falsifiable,
not diagnostic labels. Pattern reliability is tracked in the flaw ledger; a
pattern that keeps getting refuted must self-suppress (verify scoreboard).

---

## 12. Inference Calibration & Self-Correction

| ID | Setup | Expect |
|----|----|----|
| IC1 | Confirm 3 `extrapolation` hypotheses, refute 5 | rolling precision < floor (0.40) → pattern **suppressed** in next cycle |
| IC2 | User rejects an inferred fact | atom retracted, flaw ledger updated, `precision` drops |
| IC3 | Drift: stated value contradicts months of behaviour | `analyze_drift` opens a `reversal_check` / `soft_conflict` question, not a silent overwrite |

---

## 13. Source Isolation — research & notes must NOT leak

The user's standing concern. Current design: **only `source_kind="chat"`
turns are extracted.** Notes/research do not feed memory; the only link is the
*reverse* weekly diff that writes notes tagged `source_kind="memory_diff"` so
extraction skips them.

| ID | Action | Expect in `/api/memory` |
|----|----|----|
| S1 | Paste research trivia in chat: "Transformer attention scales quadratically; Mamba uses state-space models." | NOTHING about the user; at most no atoms (impersonal, low significance) |
| S2 | "Remember to check if FlashAttention-2 supports variable-length sequences." | NOT a user fact; ideally routed to tasks, never a `user·…` atom |
| S3 | Create a Note with personal-sounding text via the notes API | NO memory atom created from it (notes are not an extraction source) |
| S4 | Verify weekly memory-diff notes | tagged `memory_diff`; never re-ingested |

**Pass bar:** zero research/notes leakage into `user·…` atoms. A misfire here
is a **critical** privacy/quality failure.

---

## 14. Commitment Routing

| ID | Input (assistant makes a promise, or user states one) | Expect |
|----|----|----|
| K1 | Assistant: "I'll remind you at 9pm." | `commitment` atom AND a row in `task` (source_kind `assistant_commitment`) |
| K2 | "I'm going to call the dentist tomorrow." | commitment/plan; dated → task candidate |

---

## 15. Phrasing-Robustness (the real recall gap)

Same fact, escalating impersonality. Measures the first-person-dependence
weakness directly.

| ID | Phrasing | Predicted gate score | Should still capture? |
|----|----|----|----|
| PR1 | "I prefer small groups, max about four people." | ~0.9 (extract) | yes |
| PR2 | "Small groups are better for me, four max." | ~0.5 (coin-flip) | yes (currently flaky) |
| PR3 | "Prefers small groups, four people maximum." | ~0.25 (**skip**) | **currently NO — documents the gap** |

**Finding this surfaces:** a top-tier system should capture PR3's content when
it appears mid-conversation. Recommended remediation: augment
`_significance_score` with non-pronoun signals (named entities, life-event
verbs, "my X" possessives, declarative trait statements) so impersonally-phrased
disclosures aren't dropped.

---

## 16. Robustness & Adversarial

| ID | Input | Expect |
|----|----|----|
| A1 | Very long turn (1500+ words, the full Clay §02) | extractor returns valid JSON array, not truncated/garbage; multiple atoms; no crash |
| A2 | Mixed languages: "Je suis développeur, I live in Berlin." | text rendered in ENGLISH (rule 9) |
| A3 | Code-heavy turn with one buried fact: "```py\n...\n``` btw I switched to Neovim" | code penalty applies but the buried personal fact still captured |
| A4 | Contradiction within one turn: "I love my job but I'm quitting because I hate it." | tension preserved as two atoms; not silently resolved |
| A5 | Empty / phatic: "lol ok thanks" | no atoms; gate skips cleanly |

---

## 17. Full-Vault Integration Test (Clay)

Drive the entire Clay synthesis through as a realistic **17-session
conversation**, one cluster per turn, first-person, tier=prescient. Then grade:

**Extraction coverage (Living layer)** — expect on the order of 35–45 atoms:
identity, values, faith arc, family (dad/mum/sister/brother, dampened),
friends (Marcus/Isaac/Leo), romantic history (Mary/Valerie/May/Livia),
coping mechanisms, triggers, goals (PRISM, degree, career, Christian partner),
fears. Each with correct modality (heavy `self_perception`) and category.

**Behavioural inference (Prescient layer)** — the system should surface, as
*hypotheses shown before believed*, at minimum:
- excuse-making loop is romantic-domain-specific (B1)
- detachment dependency (B2)
- relational-impermanence belief still active despite stable friends (B3)
- productivity-worth scorecard unintegrated (B4)
- the "not-allowed rule" as a self-reinforcing belief, framed falsifiably
- asymmetry-of-impact pattern

**Conflict/coherence (Review tab)** — should open questions for genuine
tensions, e.g. stated covenant value vs documented pattern; faith conviction
vs lapsed practice — as `soft_conflict`/`reversal_check`, never silent edits.

**Hard fails to watch for:**
- Storing diagnostic labels ("has attachment disorder") — overreach.
- Injecting any inferred/hypothesis atom into chat context before confirmation.
- Collapsing nuance ("antidote received but not integrated" stored as flat
  "received antidote", losing the un-integrated half — the single most
  information-dense part of the Clay profile).
- Treating sensitive third-party abuse history as high-confidence `user` facts.

---

## Reporting template

```
CASE <ID>
  INPUT:        <verbatim>
  GATE SCORE:   <_significance_score, if measured>
  STORED:       <list atoms: subj·pred·obj | modality | cat | conf | sal>
  EXPECTED:     <from table>
  RESULT:       PASS | PARTIAL(△ reason) | MISS(✗) | MISFIRE(⚠)
```

Aggregate per section: **Precision** (stored-correct / stored-total) and
**Recall** (stored-correct / expected-total). A top-tier verdict requires
high recall in §1–§10, **non-zero meaningful inference** in §11–§12, and
**zero leakage** in §13.
