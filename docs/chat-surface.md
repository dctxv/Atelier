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
