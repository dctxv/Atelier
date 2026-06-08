# Chat Surface

*Sessions, streaming, model selection, and the composer.*

---

## Overview

The chat surface is the core of the app. It's built entirely in `chat.jsx` and connects to the backend's `/api/chat/stream` endpoint. Sessions are stored in localStorage on the client — there's no session state on the server.

---

## Sessions

Sessions are stored in `localStorage` as `atl_sessions` — a JSON array of objects, capped at 50. Each session looks like:

```json
{
  "id": "uuid",
  "name": "Session name",
  "messages": [
    { "role": "user", "content": "..." },
    { "role": "assistant", "content": "...", "model": "openai/gpt-4o" }
  ],
  "model": "openai/gpt-4o",
  "createdAt": 1717000000000
}
```

The full `messages` array is sent with every request. That's how the backend gets conversation history — the client reconstructs it and sends it each time. The backend is stateless with respect to conversations.

### Why localStorage and not the backend?

The backend (`app.py`) has file-based storage for memories, notes, and research, but not for chat sessions. I could have added a sessions endpoint. I chose not to because:

1. localStorage is instant — no round trip to read your session history
2. It's genuinely personal state — it's mine, on my machine, not something the backend needs to know about
3. If I want to clear everything and start fresh, I clear localStorage. Simple.

The downside is sessions don't survive clearing browser storage. If I were building this for multiple machines or multiple people, I'd move sessions to the backend. For now, localStorage is correct.

### Session naming

When you send the first message in a session, the session name updates to the first 50 characters of that message. It doesn't update again after that. I considered auto-generating a title by asking the model ("summarize this conversation in 5 words") but that adds latency and an extra API call. First-message naming is instant and good enough.

---

## Streaming

The backend sends `text/event-stream` responses. The client reads the stream with `ReadableStream`:

```js
const reader = resp.body.getReader();
const decoder = new TextDecoder();
let buf = '', accumulated = '';

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buf += decoder.decode(value, { stream: true });
  const lines = buf.split('\n');
  buf = lines.pop(); // hold incomplete line
  for (const line of lines) {
    if (!line.startsWith('data: ')) continue;
    const raw = line.slice(6).trim();
    if (raw === '[DONE]') break;
    const evt = JSON.parse(raw);
    const delta = evt.choices?.[0]?.delta?.content;
    if (delta) { accumulated += delta; setStreamBuf(accumulated); }
  }
}
```

The `streamBuf` state drives the live streaming display. When streaming ends, the accumulated text is written as a proper message into the session and `streamBuf` is cleared.

The streaming cursor is a 2px-wide block that blinks with a `step-end` animation — sharp on/off like a real terminal cursor. I tried a smooth fade initially but it looked too "designed." The sharp blink says "actively writing."

### Stop button

While streaming, the send button changes to a stop button (a small filled square). Clicking it calls `controller.abort()` on the `AbortController` attached to the fetch. The stream ends, whatever was accumulated is saved as the message. The response is incomplete but it's better than nothing.

---

## Message rendering

AI messages are parsed and rendered through two functions in `components.jsx`: `parseBlocks(raw)` and `renderBlock(block, idx, ...)`. There's no external markdown library — the parser is hand-written and understands exactly the block types the Atelier needs to style correctly.

### Block parsing — `parseBlocks`

`parseBlocks` processes lines sequentially, classifying each into a typed block:

| Block type | Detection | Renders as |
|---|---|---|
| `code` | Triple-backtick fence ` ``` ` | `<pre>` in IBM Plex Mono, `--surface` background, verbatim content |
| `heading` | `/^(#{1,6})\s+(.+)$/` | Cormorant Garamond, italic for h1–h2, stepping font sizes |
| `hr` | `---` / `***` / `___` | Thin `--rule` line |
| `table` | Pipe row + separator row with `-` and `|` | Real `<table>`, mono uppercase headers, Lora cells |
| `ulist` | `- ` or `* ` prefix (non-whitespace required) | Accent `–` dash + Lora text |
| `olist` | `1.` / `1)` / `1·` prefix | Accent number + Lora text |
| `paragraph` | Everything else | Lora body via `renderInline` |

Fenced code is captured verbatim before any other classification — `codeLines.join('\n')` preserves internal newlines. The code block is then rendered with `whiteSpace:'pre'` and is never touched by `renderInline` or KaTeX, so code containing `**text**` or `\(...\)` is never misfired as markup.

### Lede promotion

The first block becomes an italic Cormorant Garamond lede *only if it is a `paragraph`*. If the response opens with a heading, table, list, or code block, there is no lede — the block renders as its own type. This fixed a bug where `# Title` would become a slanted italic "# Title" because the old `parseAiContent` blindly treated the first chunk of text as the lede regardless of content.

### Inline rendering — `renderInline`

Within paragraphs, list items, and table cells, `renderInline` handles three patterns in priority order:

1. `` `code` `` — IBM Plex Mono span with `--surface` background (matched first so bold regex can't misfire inside)
2. `**bold**` — `<strong>` with `fontWeight:700`
3. Emoji codepoints — wrapped in `fontStyle:'normal'` so they aren't slanted by the italic context

Code blocks are never passed through `renderInline` — the function isn't called for `code` type blocks.

### KaTeX math

KaTeX is loaded via CDN (`cdn.jsdelivr.net/npm/katex@0.16.8`) and its CSS is in `index.html`. After streaming ends, a `useEffect` inside `AiBlock` calls `renderMathInElement` on the block's DOM node with:

- `\( ... \)` for inline math
- `\[ ... \]` for display math
- `ignoredTags: ['script','noscript','style','textarea','pre','code']` — prevents KaTeX from scanning code blocks
- The `$...$` single-dollar delimiter is explicitly *not* configured — it caused intermittent misfires when `renderInline` fragmented paragraphs into multiple text nodes around bold spans

The model persona prompt mandates `\( \)` and `\[ \]`, so removing `$` has no practical downside.

### What I considered and didn't build

**A markdown library** — I thought seriously about using marked.js or remark. Decided against it: markdown rendering introduces opinionated HTML that's hard to style to match the Atelier aesthetic, and importing a minified library is another dependency. The hand-written parser handles exactly the block types I need — nothing more.

**Syntax highlighting** — Code blocks render verbatim in IBM Plex Mono. There's no token-level syntax colouring. Adding it would mean bundling a highlighter (Prism, Highlight.js) or calling a server. Not worth it yet; readable mono is enough.

**Links** — `[text](url)` renders as plain text. The models I use rarely emit markdown links; when they do, the URL is visible in the surrounding text anyway.

---

## Model selection

The model selector is a pill button in the composer toolbar. It shows the currently active model (abbreviated) with a `◆` diamond indicator. Clicking it opens a dropdown above the composer.

The dropdown fetches `/api/models` when it opens and shows a searchable list. Selecting a model:
1. Updates the local `config` state
2. PATCHes `/api/config` with `{ active_model }` so the backend remembers it
3. Updates the active session's model field

### Model pill placement

I originally had the model name in the top tab bar as a badge. I moved it to the composer because that's where it's relevant — you're about to send a message, you want to confirm or change which model will respond. Having it in the header was just ambient noise.

The `◇ no model` state (hollow diamond) is shown when no model is configured. It's a gentle signal to run `/setup` without being an error state.

---

## Command palette

Typing `/` in the composer opens a filterable command palette above it — the same visual language as the model picker dropdown (absolute, opens upward, accent highlight on the active row, IBM Plex Mono hints on the right).

The palette is driven by a `COMMANDS` array defined inside `ChatSurface` so each command closes over the live handler functions:

| Command | Keywords | Action |
|---|---|---|
| New conversation | new, chat, session | `newSessionAction()` |
| Switch model | model, switch, pick | Opens model picker |
| Web search: on/off | web, search, toggle | Toggles `webSearch` state |
| Toggle theme | theme, dark, light, mono | Calls `onToggleTheme` from `App` |
| Set up model / endpoint | setup, model, endpoint, api, connect | Opens setup modal |
| Configure web search | setup, search, tavily, brave, provider | Opens search setup modal |
| Configure weather API | setup, weather, openweathermap | Opens weather setup modal |
| Configure stock API | setup, stock, finnhub, quote | Opens stock setup modal |

Filtering happens against both the `label` and the `keywords` array — `/web` narrows to the web-search toggle; `/setup` shows the four setup commands; `/new` shows "New conversation."

### Keyboard behaviour

- **Arrow keys** — move the highlighted row up/down
- **Enter** — runs the highlighted command, clears the composer
- **Esc** — dismisses the palette without running anything (typing more text reopens it)
- **Any `/text` that matches nothing** — `filteredCommands.length === 0` → `paletteOpen` is false → Enter falls through to `handleSend()` and the message is sent verbatim. A message like `"/etc/hosts is down"` with no matching command is treated as normal chat.

### Why I replaced the hardcoded checks

The old implementation had four exact-string comparisons in `handleSend()`:

```js
if (text === '/setup') { ... }
if (text === '/setup search') { ... }
if (text === '/setup weather') { ... }
if (text === '/setup stock') { ... }
```

These were invisible — there was no way to discover them without knowing they existed. Every time I added a new action I had to remember to add another string check. The palette fixes both: actions are discoverable by typing `/`, and adding a new command is one object in the `COMMANDS` array.

I considered building the palette in `components.jsx` as a shared component. Kept it in `chat.jsx` because it's tightly coupled to the composer state (`composer`, `paletteIndex`, `paletteDismissed`) and the handler functions. Moving it out would mean threading a lot of props or context for no real benefit.

---

## Empty state

When a session has no messages, the thread shows an empty state that changes based on whether a model is configured:

- **No model**: "Welcome" + "type /setup to add a model"
- **Model configured**: "New conversation" + "send a message to begin"

The distinction matters. If someone opens the app fresh with no model set up, they need to know what to do. If they just opened a new chat, they just need to start.

---

## Error handling

Errors display as plain italic text at the bottom of the thread in `var(--text-3)` — same color as metadata. They're not aggressive red banners. A few specific messages:

- `No model selected — use /setup or pick one below.` — when there's no model configured
- `Stream failed — check your model connection.` — when the API call fails
- Error content from the stream (e.g. `invalid API key`) is passed through from the backend

I didn't build a retry mechanism. If something fails, you just send the message again. The conversation history is intact so the context isn't lost.

---

## Thinking indicator

There was a gap between pressing Send and the first token arriving that felt dead — no feedback at all. Not a spinner in the traditional sense; I wanted something that fit the Atelier's typographic register.

What I landed on is a blinking "Thinking…" text that appears in place of the assistant response, formatted exactly like a real reply — the model colophon (`◆ model-name — The Atelier`) above it, the left accent bar beside it — but the body is just the word "Thinking…" with a CSS blink animation applied.

```css
@keyframes blink-thinking {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0; }
}
```

The animation runs at 1.4s so it pulses slowly — present, not frantic. It's in Lora italic to match the lede register, which gives it an authored rather than mechanical quality.

The timing logic in `chat.jsx`:
- `setThinking(true)` fires immediately when the user sends a message
- `setThinking(false)` fires the moment the first model delta token arrives, or the moment an `atelier_clock` or `atelier_search` event arrives (because those mean *something* is already on screen)
- If nothing arrives within the stream, clearing happens naturally when the stream ends

I considered a spinner, a progress bar, a "generating…" badge. None of them felt right — a spinner implies a network call; a progress bar implies a known completion time. "Thinking…" blinking in the response position sets the correct expectation: the model is composing a reply, not loading a page.

---

## Web search toggle

The Web toggle sits to the right of the model picker in the composer toolbar. It's a pill button with a globe icon that switches between an active (accent background) and inactive (ghost/border) state. Clicking it toggles `webSearch` in state, which is persisted to `localStorage` under the key `atl_web_search` — so if you close and reopen, the toggle is where you left it.

When the toggle is on, `web_search: true` is included in the `/api/chat/stream` request body. The backend decides whether that actually triggers a search — the toggle is the *permission*, not a guarantee.

Double-clicking the toggle (or typing `/setup search`) opens the search setup modal, which lets you paste a Tavily or Brave API key.

### Why not always-on?

For most messages the web adds cost and latency for zero benefit. "Explain the difference between FSRS and SM-2" is answered better by the model's parametric knowledge than by five web pages about SM-2. The toggle makes the intent explicit and lets me not search when I don't want to.

---

## Smart query classifier

With the toggle on, the backend doesn't call Tavily on every message — it first runs the message through two regex passes:

**`_CHAT_ONLY`** — a pattern that matches short conversational greetings and acknowledgements (`hey`, `hi`, `thanks`, `ok`, `sure`, `cool`, `lol`, etc.). These are never worth searching and were the source of an embarrassing early bug where typing "Hey" triggered five Tavily calls and returned a definition of the word.

**`_SEARCH_SIGNALS`** — a broader pattern of signals that suggest live information would actually improve the answer: event language (`breaking`, `latest`, `announced`, `died`, `strikes`), time language (`today`, `right now`, `this week`), comparison/lookup language (`vs`, `review`, `best`, `top N`), explicit year references, and so on.

```python
def _needs_web(text: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) < 6:   return False
    if _CHAT_ONLY.match(t):   return False
    if _TIME_Q.search(t):     return False  # handled by clock, not web
    return bool(_SEARCH_SIGNALS.search(t))
```

Time queries are explicitly excluded from web search here — they get the clock card path instead (see below).

The classifier is rules-only: no model call, no round-trip. It runs in under a millisecond and adds nothing to the hot path. The goal is precision not recall — it's fine to miss an edge case and reply from model knowledge. What it must prevent is the waste and noise of searching on every conversational turn.

---

## Time queries — the clock card

Asking "what time is it in Tokyo?" or "what's the current time?" gets a completely different treatment from a web search query. The model doesn't know the current time; no web search would help either (search results don't contain the current minute). What actually works is the server's system clock.

When the backend detects a time query — via `_TIME_Q`, a regex over phrases like "what is the time", "current time", "time in", "what time is it", "today's date" — it:

1. Looks for a city or timezone in the query text (matching against a small dictionary: Sydney, Melbourne, Tokyo, London, New York, Paris, Singapore, and about a dozen others)
2. Looks up the current time in that timezone using Python's `ZoneInfo`
3. If no city is mentioned, uses the server's local timezone (never UTC — UTC was the wrong default; it would show midnight-UTC and confuse anyone not thinking in UTC terms)
4. Returns structured data: `{ time, date, location, iso }`

That data is emitted to the frontend as a custom SSE event (`atelier_clock`) *before* any model tokens — then the stream immediately yields `[DONE]` and returns. **The LLM never runs.** The card is the complete answer.

```python
async def generate():
    if clock_data:
        yield f"data: {json.dumps({'atelier_clock': clock_data})}\n\n"
        yield "data: [DONE]\n\n"
        return   # ← no LLM call at all
```

The frontend `ClockCard` component renders the structured data as a clean card: the time large in Cormorant Garamond on the left (`3:42PM`), and date + timezone label on the right. No prose, no "The current time in Tokyo is…", no UTC conversion disclaimer. Just the card. Memory extraction is skipped too — there's nothing to extract from a time lookup.

This path is dramatically faster than a model reply: server round-trip + card render, no GPU involved.

### Location label edge case on Windows

Python's `datetime.strftime("%Z")` returns the full Windows timezone name on Windows — things like "AUS Eastern Standard Time" or "UTC+10:00". Those are ugly in a small UI label. The fix: derive the label from the UTC offset instead of the timezone name, formatted as `UTC+10` or `UTC+5:30`. Clean and unambiguous.

---

## Custom SSE events

The chat stream carries three event types:

| Event | Triggered when | Frontend action |
|---|---|---|
| `atelier_clock` | Time query detected | Render `ClockCard`, end stream |
| `atelier_search` | Web search ran and found results | Render `WebSearchTrace` before model tokens |
| Standard `data: {...choices...}` | Model is producing tokens | Stream into `AiBlock` |

Both `atelier_clock` and `atelier_search` arrive as the *first* event in the stream — before any model output. This means the indicator is never after-the-fact; the trace appears while the model is still generating.

The `atelier_search` event carries the real query (what actually went to the provider, which may differ slightly from the user's raw text), the provider used, whether it was cache-served, and the list of actual sources with titles, URLs, and `published_at` timestamps. No placeholders. If a source has no date, the trace shows nothing for that field.
