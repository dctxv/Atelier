# Memory Tier Selection

*Opt-in memory depth — the setup screen, the gating logic, and why nothing accumulates until you choose.*

---

## The problem this solves

Before this, memory extraction started the moment you had a model configured and began chatting. There was no moment to choose how much you wanted remembered, or what that cost you. It just ran. That's fine for a personal tool where the defaults are obvious, but memory is genuinely multi-dimensional — the cost of background model calls, the depth of inference, the presence of hypothesis generation — and those differences are large enough that they deserve a deliberate choice.

The tier system makes that choice explicit. Nothing is stored until you pick a tier. There's no backfilling of past conversations once you do — memory starts from the moment you opt in. That's both simpler to implement and more honest. You know exactly when the system started learning from you.

---

## Three tiers

Each tier is a superset of the one before it. Upgrading is additive; downgrading stops further higher-tier processing without deleting anything already built.

**Basic** — Extraction only. The cheap model runs after each chat turn, pulls structured facts about you (employer, preferences, projects, tools), and writes them as atoms. Dedup, consolidation, and chat injection all run. No background insight jobs. Estimated cost: under $0.50/month.

**Reflective** — Everything in Basic, plus the weekly stale-goal check (`memory_goal_stale`). This job scans desire and plan atoms that haven't been touched in 90 days and opens a review question for each one — "still planning to: X?" — that appears in the Review tab. It's the first tier where memory starts asking you things rather than just recording things. Estimated cost: $1–2/month.

**Prescient** — Everything in Reflective, plus the hypothesis engine (`memory_hypotheses`, weekly) and drift analysis (`memory_drift`, quarterly). The hypothesis engine generates silent, falsifiable predictions about your near-future — things it would expect to be true within 120 days given what it knows. These never appear in chat context; they're only visible in the Review surface, and they feed the calibration loop. Drift analysis walks the supersession chain for attribute and self-perception atoms and writes narrative observations about how you've changed. Estimated cost: $3+/month.

---

## Gating

### The tier flag

Two keys live in `app_config`:

- `memory.tier_selected` — `"true"` or `"false"`. Until this is `"true"`, all extraction is skipped entirely.
- `memory.depth` — `"basic"`, `"reflective"`, or `"prescient"`. Controls which background jobs run.

The extraction worker (`workers/extraction.py`) checks `memory.tier_selected` at the very top of `extract_memory`, before any significance scoring or model calls:

```python
tier_selected = str(await config.get_setting("memory.tier_selected") or "false").lower() == "true"
if not tier_selected:
    return
```

If the flag isn't set, the job returns immediately. Nothing is scored, nothing is extracted, no model is called. Chat still works; it just operates without memory accumulation. A user can chat for weeks before opting in and zero atoms will have been written.

### Prescient job gating

Each of the three background jobs in `workers/memory_prescient.py` checks `memory.depth` before doing any work:

- `generate_hypotheses` — returns early unless depth is `"prescient"`.
- `analyze_drift` — same.
- `check_stale_goals` — returns early unless depth is `"reflective"` or `"prescient"`.

This means the scheduler still fires all three jobs on their normal cadence regardless of tier — the check is inside each job function, not in the registration logic. That keeps the scheduler simple.

---

## API

Two endpoints on the memory router (`routers/memory.py`), declared before all parameterized routes to avoid path ambiguity:

```
GET  /api/memory/tier      → { tier_selected: bool, depth: string }
POST /api/memory/tier      → { ok: true, depth: string }
                             body: { depth: "basic" | "reflective" | "prescient" }
```

`GET` reads both config keys and returns them. `POST` validates the depth value, then writes both `memory.tier_selected = "true"` and `memory.depth = depth` atomically via the config service.

---

## The setup screen

When the Memory surface loads, `MemorySurface` fetches `/api/memory/tier` alongside all other data in its initial `Promise.all`. If `tier_selected` is `false`, it renders `TierSetupScreen` instead of the normal dashboard — not a modal, but the entire content area.

The setup screen is non-scrollable and fully centered in the content area. It has a small uppercase label ("Memory Setup"), a Cormorant Garamond italic heading, a subdued sub-line, the three tier cards in a flex row, and a footer note about upgrade and downgrade behavior.

### Tier cards

Each card has the same structure:

1. A 2px accent bar at the top in the tier's color (teal for Basic, blue for Reflective, violet for Prescient).
2. A tier name and tagline.
3. A hairline divider.
4. For Reflective and Prescient, an "Everything in [previous tier], plus:" line.
5. All feature bullets — no collapsing. Each bullet has a 3px dot in the accent color at 60% opacity.
6. A static "How does it work?" line (unfunctional for now — a placeholder for future documentation linking).
7. A footer with the estimated cost and an "Enable [Tier]" button.

The enable button uses the accent color as a semi-transparent background (`rgba(accent, 0.1)`) with a matching border (`rgba(accent, 0.32)`) and the accent color as text — a contained but not filled style. When one card is saving, the other two drop to 40% opacity.

The accent colors are intentionally distinct from the project's warm terracotta accent:

| Tier | Accent |
|---|---|
| Basic | `#2dd4bf` (teal) |
| Reflective | `#60a5fa` (blue) |
| Prescient | `#a78bfa` (violet) |

The card backgrounds and borders use the project's standard tokens (`var(--nav-bg)`, `var(--border-2)`) so the cards fit naturally into both the Natural and Mono themes. Only the accent colors are fixed hex values.

### After selection

Clicking "Enable [Tier]" calls `POST /api/memory/tier`, then calls `onTierSelected(depth)` which sets `tierSelected` in component state and re-runs `loadData()`. The setup screen is replaced by the normal memory dashboard. No page reload.

---

## Returning to the selector

After a tier is chosen, a small pill button appears at the far right of the Memory tab bar. It shows the current tier name — `basic`, `reflective`, or `prescient` — in 10px mono. Clicking it sets `tierSelected` to `false` in local state, which immediately renders the setup screen again. If the user picks a different tier, the POST updates the backend. If they navigate away without picking, the backend still has the old tier — the state change is local-only until a new `Enable` is clicked.

---

## Settings integration

The Settings surface has a Memory section (`MemoryTierSection` in `static/settings.jsx`) accessible from the left nav rail. It shows the three tiers as radio buttons with their names, cost badges, and short descriptions. The current tier is labeled `current`. Changing the selection reveals an inline notice — "Upgrading takes effect immediately" or "Downgrading stops further higher-tier processing. Existing memories are kept." — alongside a Save button. The save POSTs to `/api/memory/tier` identically to the setup screen flow.

If no tier has ever been selected, the settings section shows a note directing you to the Memory page instead of radio buttons, since the full setup screen is the right first-time experience.

---

## What I considered

**Auto-starting extraction at a default tier.** The obvious simpler version is: pick a default (Basic) and start extracting, then offer an upgrade path later. I decided against it because the cost question is the most important thing to surface up front. Even Basic has a non-zero cost, and more importantly the presence of extraction at all — even cheap extraction — is something the user should actively opt into. A personal tool that silently starts logging things about you, even benign things, is doing something without your knowledge. The explicit choice felt important.

**Backfilling past conversations when a tier is selected.** Once you enable memory, it would be technically possible to re-ingest recent chat history and retroactively populate atoms. I decided not to do this. Backfilling means running model calls over conversations the user didn't intend for memory, and the result would be a memory corpus the user can't trust — they'd have to review everything to understand what was inferred and when. Starting clean from opt-in is simpler and more honest.

**A single "memory on/off" toggle instead of three tiers.** Most of the UI would be simpler with just on/off. The reason for three tiers is cost transparency: the hypothesis engine and drift analysis are meaningfully more expensive than basic extraction, and they do qualitatively different things (inference and narrative, not just recording). A single toggle obscures that. The tier model lets someone who just wants clean fact-recording opt into that without paying for weekly model jobs they don't care about.

**Destroying memories on downgrade.** When you go from Prescient to Basic, you've accumulated hypothesis atoms, insight atoms, and narrative observations that Basic doesn't generate. The question is whether those should be deleted. I kept them. The user might have confirmed hypotheses and referenced insights; deleting them on tier change would lose real data. Downgrading stops further generation of those atom types, but what's already there stays. If the user wants to purge them, that's a manual operation.
