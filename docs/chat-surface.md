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

AI messages go through `parseAiContent()` before rendering. This splits the text into a lede (opening paragraph) and body (everything after the first double newline). The lede renders in Cormorant Garamond italic at 21px. The body renders in Lora at 16px. If the lede is very long (over 300 chars), it's further split at the first sentence boundary so the lede stays short and punchy.

This was a deliberate design call. Most AI responses have a natural opening — the summary statement before the explanation. By separating it visually, that structure becomes legible. Not every response splits cleanly, but most do.

### What I considered and didn't build

**Full markdown rendering** — I thought seriously about using a markdown library (marked.js or remark) to render headers, bullet lists, code blocks, bold, italic, links. I didn't for a few reasons. Markdown rendering introduces opinionated HTML that's hard to style to match the Atelier aesthetic. The backend models I use don't always produce clean markdown — sometimes they mix markdown with prose in ways that render weirdly. And importing a markdown library (even minified) is another dependency.

What I built instead is a minimal inline renderer: `**bold**` becomes `<strong>`, and emoji characters get wrapped in `fontStyle:'normal'` so they don't appear slanted. That handles the 80% case without the complexity.

**Code blocks** — Not implemented. If a response contains a code block with triple backticks, it renders as plain text. This is a known gap. When I add it, I'll wrap it in `<pre>` with IBM Plex Mono and a surface background. But I wanted to ship something that worked rather than stall on syntax highlighting.

**Tables** — Not implemented, same reason.

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

## /setup slash command

Typing `/setup` in the composer and pressing Enter triggers the setup modal instead of sending a message. The detection is a simple string comparison:

```js
if (text === '/setup') { setComposer(''); if (onSetup) onSetup(); return; }
```

It has to be the entire message — just `/setup`, nothing else. I chose this over a slash-command parsing system because I only have one slash command right now. When there are more, I'll build a proper command palette. Until then, a string check is enough.

I considered showing a slash command suggestion popup when you type `/` — the way Notion or Slack shows a command menu. Decided against it for now because it's UI complexity for a feature with one command.

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
