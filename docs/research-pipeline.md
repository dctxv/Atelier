# Deep research

*You ask a question; the Atelier reads the web, writes a sourced answer, and remembers what it found. This page is the running story of how the feature has grown — newest first — followed by a plain-English guide to how it works and how to read a report. No coding background needed.*

---

## Progress log

This section is a timeline, not a snapshot. Each entry stays here so you can see how the feature has evolved — what it could do then, and what it can do now.

### v2.4 — A sharper checker and a deeper dig *(latest)*

Two follow-ups after watching real reports:

- **The checker now reads the whole source passage.** It was only looking at the first ~400 characters of each ~1,000-character excerpt, so when the confirming detail sat further down the page it wrongly said "doesn't support" — which inflated the "unverified" count. It now reads ~900 characters, so it judges on the full passage.
- **It digs deeper now.** Earlier runs sometimes stopped after a single round of searching because the quick "are there gaps?" check declared itself satisfied too easily. There's now a **minimum of two rounds** (whenever there are still useful follow-up questions), the gap-check is told to *always* suggest follow-up angles, and each sub-question pulls **more pages** — so the pool of evidence is bigger and more varied, which also gives the corroboration step more independent sources to confirm a claim with.

*Trade-off, stated honestly:* deeper digging means a report takes longer and uses a bit more of the model budget. That's the cost of fewer "unverified" claims and more genuinely "supported" ones.

### v2.3 — Making "supported" actually reachable

A review of the stored data found that across 57 claims, **none** had ever been marked "supported" — every claim was "single source" or "unverified." It turned out this wasn't the checker being harsh; it was structural:

- The writer was citing **one source per claim** about two-thirds of the time, and "supported" by definition needs **two independent sources** that both confirm the claim. A one-source claim simply can't get there.
- The cheap checker was also marking about half of cited sources "neutral" (related, but not a direct confirmation), which knocked even two-source claims down to one.

Three changes fix this:

- **A corroboration step.** When a claim has fewer than two independent confirming sources, the system now actively scans the *rest* of the gathered material for a supporting source from a **different** website and checks it. So a claim the web genuinely backs can now reach "supported" instead of getting stuck at "single source" just because the writer happened to cite only one place.
- **A more diverse source pool.** The pool of material the writer and checker draw from is now spread across more distinct websites (capped per site), so independent corroboration is actually available.
- **Neutral citations look different now.** A source that was cited but judged *not* to directly support a claim shows with a **dotted, greyed** number (e.g. a muted `[8]`) and a tooltip, instead of looking identical to a confirming source. This is why a sentence could show `[10][8]` yet read "single source" — only `[10]` actually confirmed it; `[8]` was related but neutral. Now you can see that at a glance.

*Why this matters:* "supported" is the label that's supposed to mean "more than one independent source agrees." It should be earned, not impossible — and now it's both.

### v2.2 — Full transparency about evidence

The goal of this round was simple: **never hide what the system did.**

- **Set-aside sources are now shown, not discarded.** When the writer cites a source but the checker decides it's too weakly related to count, that source used to silently vanish — leaving sentences with no citation at all. Now it's kept and labelled **"set aside,"** so you can see exactly what was considered and click through to judge for yourself.
- **The relevance bar was lowered** (from 0.45 to 0.30 on the similarity scale). The old setting was too strict and was throwing away genuinely useful sources, which made too many claims look unsupported. Fewer real sources get set aside now.
- **Every claim is traceable.** A claim either shows the sources that back it, the sources that were set aside, or an explicit "no source cited" note. Nothing is left unexplained.

*Why this matters:* the earlier behaviour produced confusing "unverified" sentences with nothing attached. That wasn't dishonesty — it was the checker correctly discarding weak links — but it looked like a black box. Now the box is open.

### v2.1 — Readable, trustworthy, and it stops disappearing

- **Claim cards + a Read/Claims toggle.** The report can be read as normal prose (**Read**) or broken into individual verified cards (**Claims**). Same content, two levels of scrutiny.
- **Honest counts.** The progress bar used to say "109 sources" when it really meant 109 *text passages* — and the final report cited about a dozen. The numbers are now labelled plainly: pages **examined** vs. sources **cited** vs. **passages** looked at (see "Being honest about the numbers" below).
- **It no longer disappears.** Previously, clicking away while a report was being written lost the half-finished answer. Now every section and claim is saved the instant it's produced, so you can leave, switch reports, or reload and find it exactly where it was.

### v2 — The claim loop (Analyst Mode)

This was the big leap from "search summary" to "research engine":

- **Iterative deepening.** Instead of one planning pass, the system works in rounds: after each round it checks for gaps and writes follow-up questions, going deeper where the topic needs it.
- **Claims, not just prose.** The answer is built as individual, checkable statements, each tied to the sources behind it.
- **Verification.** Every claim is re-checked against its sources and given a **confidence** score and a **stance** (supported / disputed / single-source / unverified).
- **Contradiction detection.** Where sources genuinely disagree, the report flags it instead of quietly picking a side.
- **Inline citations.** Numbered markers link each statement to the exact source.
- **Personal grounding.** Before searching, it reads what you've already told the app, so answers can be personal.
- **Live streaming + freshness.** Progress shows as it happens, and time-sensitive questions favour recent sources.

### v1 — The baseline *(for the record)*

The original version: a planner split the question into up to five sub-questions, searched them all in parallel, ranked what it found, and wrote a single grounded report with a flat list of source links. It had **no** claims, **no** confidence, **no** contradiction flags, **no** follow-up rounds, and **no** inline citations — and the in-progress report was lost if you navigated away. Everything above is what's been added since.

---

## What it does, in one paragraph

You type a question into the Research surface. In the background the Atelier breaks your question into smaller ones, searches the web for each, reads what it finds, and writes up an answer. The answer isn't just an essay: it's a set of **claims** — individual, checkable statements — and each claim shows how confident the system is, which sources back it up, and whether sources disagree. The important findings are also saved into the app's memory, so later, in chat, the Atelier already knows what the research turned up without you re-running it.

It runs as a **background job**, so you can leave the page, do something else, and come back — the work keeps going and nothing is lost.

---

## How it works, step by step

Think of it as a small research team working in stages:

1. **It checks what it already knows about you.** Before searching, it looks in the app's memory for anything relevant you've told it before, so the answer can be personal rather than generic.
2. **It plans.** A fast, inexpensive model turns your question into up to five focused sub-questions.
3. **It searches and reads, in rounds.** For each sub-question it searches, opens the top results, and reads them. After each round it asks itself *"have I actually answered this, or are there gaps?"* and, if needed, writes new sub-questions and goes again — up to three rounds. This is **iterative deepening**.
4. **It writes the answer as claims.** A more capable model turns the best material into short, specific, checkable statements, grouped into sections, each pointing back to its sources.
5. **It checks each claim.** For every claim it re-reads the cited sources and asks: *do these actually support this, contradict it, or not really address it?* From that it produces a **confidence** score and a **stance** label.
6. **It links the ideas together.** A final pass pulls out key concepts and how they relate, and saves them for future use. *(The visual concept-map is not built yet — see "Still on the list.")*
7. **It saves everything and updates memory.** The report, claims, evidence, and sources are stored; the strongest findings are added to memory.

---

## Reading the report

At the top you'll see the title, a short summary, and a stats line. A toggle lets you switch between two ways of reading the same content.

### Two views: Read and Claims

A small **Read / Claims** toggle sits at the top-right of the report.

- **Read** (the default) shows the answer as flowing prose, like an article. Each statement has small numbered source markers and a faint colored underline showing how well-supported it is. **Hover over a sentence** to see its confidence, stance, and any set-aside sources.
- **Claims** breaks the same content into one card per statement, with confidence and stance shown plainly beside each — for when you want to audit the answer claim-by-claim.

### What the labels mean

Each claim carries a **stance** — the system's read on how well the sources back it:

| Label | Color | Meaning |
|---|---|---|
| **Supported** | green | Two or more independent sources agree. The strongest kind of claim. |
| **Disputed** | red | Sources disagree — at least one contradicts it. Worth a closer look. |
| **Single source** | brown/accent | Only one source backs it. Plausible, but not independently confirmed. |
| **Unverified** | grey | The check couldn't confirm it against the sources (see below). Treat with caution. |

A **confidence** bar (0–100%) gives a finer sense of how strongly the evidence held up.

### "Unverified" and "set aside" — what they really mean

These two come up a lot, and they're the heart of the transparency work, so here's the plain version:

- When the writer makes a claim, it names the sources it used.
- The checker measures how closely each named source actually matches the claim. If a source is too loosely related to count as real evidence, it's marked **"set aside"** — still shown, still clickable, just not counted toward confidence.
- If, after that, **nothing clearly supports and nothing contradicts** the claim, it's labelled **unverified**. This usually means one of two things: the writer added a general linking sentence that wasn't really pinned to a source, or the sources were related but the checker couldn't confirm a direct link.

The key change in v2.2: an unverified claim no longer appears as a bare, source-less sentence. You'll see either its set-aside sources or an explicit **"no source cited"** note — so you always know *why* it's unverified.

### Citations

Numbers like `[1]` `[2]` after a statement are **citations** — click one to open that exact source. They match the **Sources** list on the right. This is how you check any claim yourself. A muted **"set aside [4]"** means the system looked at source 4 but decided it didn't really support the point.

### The contradiction banner

If genuine disagreement is found between sources, a **contradictions** box appears near the top listing the conflicting points. Instead of quietly averaging the two, the report *shows you* the conflict and lets you judge — often the most useful part for messy or fast-moving topics.

---

## Being honest about the numbers

The report may say **"9 cited of 42 examined."** Here's exactly what that means:

- **Examined** = how many distinct web pages the system actually opened and read (often 30–45).
- **Cited** = how many of those were good enough to quote in the final answer (usually around a dozen).

While running, the live status also mentions **passages.** A long page is split into several shorter **passages** so each part can be weighed separately — so one page can become three passages. That's why mid-run you might see "100+ passages examined": those are *text fragments*, not separate websites.

The short version: it reads a few dozen real pages, looks at them in finer pieces, and cites the best dozen or so — and the report states these numbers plainly rather than inflating them.

---

## Still on the list

- **The concept map.** The connections between ideas are already extracted and saved; the visual map to display them isn't built yet.
- **Remembering your view choice.** The Read/Claims toggle resets to *Read* on reload; it could remember your preference.
- **Re-run / refine from the page.** For now, to redo a report you delete it and ask again.

---

## For the technically curious

The pipeline lives in `workers/research.py` (the background job), with results stored and served via `services/research.py` and `routers/research.py`, and rendered by `static/research.jsx`. It builds on the shared **search layer** ([web-search.md](web-search.md)) — inheriting caching, freshness handling, the provider fallback chain, and local reranking — and the **memory hub** ([memory.md](memory.md)) for the personal-context lookup at the start and the findings saved at the end. The claim/evidence/entity tables were reserved ahead of time in [v2-deferred.md](v2-deferred.md); this is their built form. The "set aside" mechanism is the relevance gate in `_verify_claim` (`EVIDENCE_MIN_COS`), which now records weak citations instead of dropping them.
