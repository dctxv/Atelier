# Inline Rendering

*How AI text is formatted — bold, emoji, and what's still missing.*

---

## The problem

AI responses arrive as plain text strings. The backend doesn't pre-process them. The frontend renders that text directly into React elements — which means anything the model outputs that looks like formatting (like `**bold**`) just appears as literal asterisks on screen.

Two specific problems were noticeable:

1. **Emoji rendered slanted** — The lede paragraph uses `fontStyle: 'italic'` on Cormorant Garamond. Emojis don't have an italic variant, but the browser tilts them when they inherit `fontStyle: italic`. A 😊 in a response would appear at a slight slant, which looks broken.

2. **Bold text showed as `**word**`** — Models frequently use `**text**` for emphasis. Nothing was parsing it, so the asterisks appeared literally.

---

## The solution — renderInline()

Rather than pull in a markdown library, I wrote a minimal inline renderer — a single function that handles just these two cases. It lives in `components.jsx` so it's available to everything.

```js
function renderInline(text) {
  if (!text) return text;
  const re = /\*\*([^*\n]+)\*\*|([☀-➿]|\uD83C[\uDF00-\uDFFF]|\uD83D[\uDC00-\uDEFF]|\uD83E[\uDD00-\uDDFF])/g;
  const out = [];
  let k = 0, i = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > i) out.push(text.slice(i, m.index));
    if (m[1] !== undefined)
      out.push(<strong key={k++} style={{ fontWeight: 700 }}>{m[1]}</strong>);
    else
      out.push(<span key={k++} style={{ fontStyle: 'normal' }}>{m[2]}</span>);
    i = m.index + m[0].length;
  }
  if (i < text.length) out.push(text.slice(i));
  return out.length ? out : text;
}
```

It returns an array of strings and React elements — the same thing React expects as children. Applied to the lede, body paragraphs, numbered list items, and user messages (which also use italic styling).

### Bold: `**text**` → `<strong>`

The regex `\*\*([^*\n]+)\*\*` matches bold spans. The capture group excludes asterisks and newlines so it can't accidentally span multiple paragraphs or nest. The `<strong>` gets `fontWeight: 700` explicitly — not relying on the browser default bold, which can be inconsistent across font faces.

### Emoji: upright override

The emoji ranges in the regex cover the most common emoji Unicode blocks via surrogate pairs:
- `[☀-➿]` — common symbols in the BMP (U+2600–U+27FF range, roughly)
- `\uD83C[\uDF00-\uDFFF]` — nature, food, travel, activities emoji
- `\uD83D[\uDC00-\uDEFF]` — faces, people, objects
- `\uD83E[\uDD00-\uDDFF]` — newer emoji (animals, food, gestures)

Each matched emoji gets wrapped in `<span style={{ fontStyle: 'normal' }}>`. This explicitly overrides the inherited italic, so the emoji appears upright regardless of what the parent paragraph's style is.

### Why not Unicode property escapes?

The cleaner modern approach would be `/\p{Emoji_Presentation}/gu` with the `u` flag. I avoided it because Babel standalone's `preset-env` may or may not transpile Unicode property escapes depending on the target, and I didn't want to debug transpilation edge cases. The surrogate pair approach works everywhere without needing the `u` flag.

---

## What renderInline doesn't handle

These are known gaps. They're not bugs — they're scope decisions.

**`*single asterisks*`** — single-asterisk italic. The lede is already italic, and Lora body text is roman, so `*word*` would actually look correct in body but wouldn't render anything special in the lede (italic of italic is a typographic double-negative). I left it out because the behavior would be inconsistent across lede vs. body, and the models I use mostly use double asterisks for emphasis anyway.

**`` `code spans` ``** — backtick code. Would render as IBM Plex Mono with a slight background tint. A real gap — models use inline code fairly often. Next thing to add.

**`[links](url)`** — markdown links. Not rendered. Would become `<a>` tags. The security consideration here is worth thinking through — user-visible URLs from AI output. I'd want to sanitize or at minimum set `rel="noopener noreferrer"` before shipping this.

**`# headings`** — not handled. If a model outputs a heading in the response, it renders as a line starting with `#`. Headings would require block-level parsing (not inline), which means restructuring how paragraphs are split and rendered.

**`- bullet lists` / `1. numbered lists`** — the `parseAiContent` function has a basic numbered list pattern (`/^(\d+\s*[·.])\s+([\s\S]+)$/`) for lines like `1. item`, but not for markdown `- item` bullets. Those render as lines starting with `-`. Adding bullet detection would be a straightforward extension to the same paragraph-splitting logic.

**Code blocks (triple backtick)** — A meaningful gap. The whole block renders as plain prose. Adding this would require detecting `` ``` `` fence markers during the paragraph split phase and rendering with a `<pre>` / Plex Mono treatment.

---

## Why not just use marked.js or remark?

A proper markdown parser would solve all of the above in one go. I have two reservations:

**Styling conflict**: Markdown libraries produce semantic HTML (`<h1>`, `<ul>`, `<li>`, `<blockquote>`) with browser default styles. To make that match the Atelier's typographic system, I'd need to write CSS resets targeting all of those elements — inside `.ai-response` or similar. That's a maintenance surface I'd rather not have if I can avoid it.

**Model output isn't clean markdown**: The models I use mix markdown syntax with prose in ways that don't always parse cleanly. A `**bold**` phrase at the start of a sentence followed by a period-less paragraph will trip up most parsers. The custom renderer only attempts to handle what it understands, and passes everything else through as plain text. That's more forgiving.

The right long-term decision is probably a light markdown parser with the Atelier design system's styles applied to the output elements. But I'd want to do that as a deliberate redesign pass, not a quick addition.
