# Surfaces — Memory, Notes, Research

*The three non-chat surfaces and how they connect to the backend.*

---

## Memory surface

### What it is

The memory surface shows two things side by side in the same scrollable view: memory fragments and skills.

**Memory fragments** are short text records stored by the backend — things learned about you during conversations. The backend categorizes them (preference, identity, goal, contact, task, project, fact). I remapped those to simpler display labels: preferences, people, decisions, projects, facts. The raw backend category names aren't user-facing vocabulary.

Fragments are grouped by their display tag, each group with a colored dot indicator and an uppercase mono label. The left accent bar motif from the chat surface appears here too — each fragment has a thin colored vertical rule. The color maps to the tag type (warm amber for preferences, a teal for people, etc.) at reduced opacity so it's subtle.

**Skills** are configured behaviors the backend can run. Each skill has a name, optional description/when-to-use text, and an enabled state. You toggle them with a custom toggle component (a sliding pill — not a browser checkbox, because the native checkbox doesn't style to match the rest of the UI).

### API quirks fixed

The backend uses `memories` as the key (plural). An earlier version of the surface code used `memory` (singular), matching a different backend's convention. Fixed to try both: `memData.memories || memData.memory`.

The skill toggle API is `POST /api/skills/{id}/toggle` — not a PUT or PATCH. I updated this from the original version which was using `PUT /api/skills/{id}`. This matters because the backend only registers the `/toggle` route.

Skill `enabled` state is read from `sk.enabled !== false` — a truthy default. The backend stores `enabled: true/false` but older records might not have the field at all, in which case `!== false` defaults to enabled. This is safer than checking `sk.status === 'active'` which was an Odysseus-era convention that doesn't apply to the real backend.

### What I didn't build for memory

**Editing or deleting memory fragments** — The backend doesn't expose a delete or update endpoint for memories, so there's no UI for it. I left the display read-only rather than building a delete button that would silently fail.

**Adding memories manually** — Same reason. If the backend adds a `POST /api/memory` endpoint later, I'll add a form here.

**Search highlighting** — The search filter works (it hides non-matching fragments), but matching text isn't highlighted in the results. Would be a nice touch to add later.

---

## Notes surface

### What it is

A classic two-pane notes editor. Left panel: note list with search, sort (pinned first, then by updated date), shimmer skeleton loading state. Right panel: a bare-bones editor with a title and body textarea, auto-saving every 1.5 seconds after any change.

The editor is intentionally minimal. No formatting toolbar, no markdown preview, no rich text. Just a Cormorant title and Lora body. Notes are for writing things down, not for formatting them.

### Autosave

Saves fire 1.5 seconds after the last keystroke (debounced via `setTimeout`). There's also a save on blur (when you click away). The save state is shown in the top-right of the editor toolbar: "unsaved" while dirty, "saving…" during the request, "saved" after.

I considered a manual Save button instead of autosave. Decided that for notes, autosave is the right default. The risk of losing unsaved work outweighs the risk of saving something you didn't mean to. You can always delete a note or edit it.

### API field name

The backend stores note body in a field called `body`. An older version of this code used `content` (matching a different API schema). The fix is everywhere `content` appears in read/write operations — replaced with `body`.

### What I didn't build for notes

**Markdown preview** — The editor is a plain textarea. If I add a preview mode, I'll add a toggle in the toolbar. For now, the writing experience is more important than the reading experience for notes.

**Tags or folders** — No organization beyond pinning. For the volume of notes I currently have, search is enough. If it gets unwieldy, I'll add a tag system.

**Export** — No way to export a note to text, markdown, or PDF. Would be useful to add.

**Keyboard shortcut to create a note** — You have to click the `+` button. A `Cmd+N` or similar shortcut would be a nice addition.

---

## Research surface

### What it is

A three-panel layout: library (left), document (center), sources (right). The library shows all past research sessions. The document shows the selected session's report. Sources appear conditionally on the right when a report has them.

Starting a new research session: you type a query in the input at the top of the library panel and press Enter (or click the send icon). This calls `POST /api/research/start`. A placeholder item appears in the library immediately with a `running` status indicator (the breathing pulse dot). Polling starts at 3-second intervals to check for completion. When done, the report loads automatically.

### Report rendering

The report text goes through the same `parseAiContent` split as chat — first double-newline creates a lede/body split. The lede renders in Cormorant italic, body in Lora paragraphs. The left accent bar appears here too. The research surface reads like the chat surface — same typographic logic, same hierarchy.

### Status indicators

- `running` — the breathing pulse dot (`<Pulse/>`)
- `done` — a small filled circle at 50% opacity
- anything else (queued, error) — a hollow circle outline

These appear in the library list next to each item. Simple enough to scan at a glance.

### API path changes from previous version

The research endpoints changed between an older frontend version and the real backend:

| Old (wrong) | Correct |
|---|---|
| `/api/research/library` | `/api/research` |
| `/api/research/detail/{id}` | `/api/research/{id}` (unwraps `{ research: item }`) |
| `/api/research/status/{id}` | `/api/research/{id}` (same endpoint, check `status` field) |

### What I didn't build for research

**Deleting research sessions** — No delete button. The backend presumably supports deletion but I haven't wired it up yet.

**Re-running a query** — If you want to run the same query again, you have to retype it. A "Re-run" button per item would be useful.

**Inline source citations** — The sources panel shows numbered sources. The report text doesn't link to them. Making citation numbers in the report text clickable (scrolling the sources panel to that source) would make the research surface much more useful as an actual reading interface.

**Filtering/sorting the library** — The library is in reverse-chronological order with no filtering. A search or date-range filter would be useful once there are many sessions.
