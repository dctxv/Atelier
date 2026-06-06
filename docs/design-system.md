# Design System

*The visual language of The Atelier v2.*

---

## The direction I chose

The design went through a few directions before landing on what's there now. The one I ultimately went with is what I was calling "Direction 2b — Open Study refined." The shorthand for it: editorial, not chat.

Most AI interfaces look like messaging apps. Bubbles, timestamps, avatar icons. That works fine but it doesn't feel like thinking — it feels like texting. What I wanted instead was something closer to reading a well-typeset document. The AI's response appears as a piece of writing, not a text message. It has a lede. It has body. It has a left accent bar like a pull quote. That's the core idea.

---

## Typography

Three fonts, each with a specific job.

**Cormorant Garamond** — the display face. Used for the AI response lede (the opening sentence or two), modal headings, and anything that needs weight and presence. It's a free revival of Garamond with excellent italics. The italicized version in the lede gives the response an almost hand-written, authored quality. I had considered using Playfair Display here, but Cormorant is more restrained. Playfair can feel a bit performative.

**Lora** — the body text face. Used for the bulk of AI responses, notes, longer reading. Lora is a contemporary serif designed for screen reading. It's warmer than something like Georgia and holds up at 15–16px. I briefly considered using Tiempos Text (a paid font I like a lot) but it requires licensing and I didn't want the Atelier to depend on anything that costs money or has restrictions.

**IBM Plex Mono** — the label face. Used for UI labels, section headers, timestamps, model names, tab index numbers, everything that needs to be clearly "interface" rather than "content." The mono quality makes it feel technical and precise without being cold. I had considered using JetBrains Mono here but it's too code-editor — Plex Mono has a slightly more editorial feel.

All three are loaded from Google Fonts. The downside is that this requires an internet connection for the fonts to display correctly. If fonts fail to load, the fallbacks (Georgia, monospace) are fine but noticeably less refined. At some point I'd like to self-host the font files the same way I self-host the React and Babel libs.

---

## Color tokens — Natural theme

The natural theme is the default. It's warm parchment tones — like an old book or a well-worn notebook. Nothing stark, nothing neon.

| Token | Value | Role |
|---|---|---|
| `--bg` | `#F6F1E7` | Page background |
| `--surface` | `#EDE6D8` | Panel/sidebar background |
| `--thread-bg` | `#FAF6EE` | Main reading area background |
| `--text` | `#18130E` | Primary text — very dark warm brown, not pure black |
| `--text-q` | `#7A6A58` | Secondary text — user messages, dimmer labels |
| `--text-3` | `#C4B09A` | Tertiary — timestamps, metadata |
| `--accent` | `#8A5A34` | Warm amber-brown — used for active states, borders, the left bar |
| `--send-bg` | `#8A5A34` | Send button background |
| `--send-fg` | `#FFF4E8` | Send button text/icon |

The accent color is important. It's the only "color" in the interface — everything else is neutral. It needed to feel natural and warm without feeling generic. I tried a few alternatives: a terracotta, a muted gold, a sage green. The warm brown won because it felt most consistent with the parchment background. It doesn't fight anything.

---

## Color tokens — Mono theme

The mono theme is for people (including me, at night) who want something near-black. It shares the same token names so the entire UI switches with a single `data-theme` attribute on `<html>`.

| Token | Value | Role |
|---|---|---|
| `--bg` | `#0D0D0D` | Near-black page background |
| `--surface` | `#131313` | Panels |
| `--thread-bg` | `#0B0B0B` | Slightly darker than surface — reading area |
| `--text` | `#E0DCD4` | Warm white — not pure white, keeps warmth |
| `--accent` | `#9A9288` | Muted warm grey |

The mono theme is deliberately desaturated. I didn't want a traditional "dark mode" with blue tints or high-contrast purple accents. The whole point is that it should feel like the same workspace at night — quieter, not different.

---

## What I didn't do with themes

I considered adding more themes — a "paper white" high-contrast mode, maybe something with a blue accent for a different mood. I held off because three fonts and two themes is already a lot of surface area to keep consistent. If I add a third theme without a design token audit, things get out of sync fast.

I also considered a theme picker with more than two options — like a full color picker for the accent. Decided against it. Having too many customization options makes the product feel like a settings panel rather than a tool. Two themes is enough.

---

## Animation

Four keyframes, each with a specific purpose:

- **`fadeUp`** — new content enters from slightly below. Used on every AI message and each surface when you navigate to it. 7px of travel, 380ms. Feels like the content surfacing rather than snapping in.
- **`breathe`** — the pulse dot in the bottom-left of the nav rail, and the loading indicators. Fades from 100% to 25% opacity on a 2.8s loop. Slow enough to be calm.
- **`writing`** — the streaming cursor (a 2px wide block). Step-end timing so it blinks sharply like a real cursor.
- **`shimmer`** — skeleton loading state. Used in the notes list while loading. A gradient sweep across a placeholder block.

I originally had the AI messages using a different animation — a horizontal slide from the left, like the response coming from the left accent bar direction. I dropped it because with longer responses it looked twitchy. The vertical fadeUp is gentler.

---

## Left accent bar

The vertical bar on the left side of every AI response (`--bar`, 1.5px wide) is the visual anchor of the whole design. It's borrowed from the pull-quote convention in editorial design — a thin rule that signals "this is a quoted or highlighted passage." Here it signals "this is the AI's authored response." It distinguishes AI output from everything else without needing color, bubble backgrounds, or avatars.

The bar color uses `rgba` so it softens slightly rather than being hard. At full opacity it would be too assertive.
