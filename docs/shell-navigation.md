# Shell & Navigation

*The left rail, chat tab bar, and how you move around.*

---

## Left rail

The left rail is 54px wide and contains four things:

1. The "A" wordmark — a small rounded tile with the Cormorant Garamond "A" in accent color
2. Navigation icons — chat, research, memory, notes, tasks, files
3. Theme toggle — sun/moon icon at the bottom
4. The pulse dot — a slowly breathing indicator at the very bottom

The navigation is icon-only with no labels. I thought about adding labels — either always visible, or on hover with a tooltip. I went icon-only for a few reasons. First, six icons in a 54px column leaves very little horizontal space for text that would be readable. Second, the icons are conventional enough (chat bubble, magnifier, brain, document) that the meaning is clear without labels. Third, text labels would make the rail feel busier. The tooltip on hover (via `title` attribute) is there as a fallback if someone genuinely can't place an icon.

The rail is purely presentational — it just calls `onNav(id)` when you click, and the active state is indicated by an accent background + border on the active icon. No routing library, no URL changes. The current surface is stored in localStorage (`atl_surface`) so it persists across page reloads.

### What's in the nav that isn't fully built yet

Tasks and Files are in the nav but show a "coming soon" placeholder when you click them. I included them in the nav intentionally — having them there makes the space feel complete and sets expectations for what the Atelier will eventually be. Removing them from the nav until they're built would mean the nav changes shape, which is disorienting. Better to have the slots reserved.

---

## Chat tab bar

The tab bar sits above the chat thread and shows all current sessions as horizontal tabs. It's probably the most technically interesting UI piece in the whole frontend.

### Scrolling

Tabs overflow horizontally. You scroll the tab bar with the mouse wheel or by clicking and dragging. Both of these required non-standard implementations.

**Wheel scroll**: React's `onWheel` handler attaches with `{ passive: true }` by default, which means you can't call `e.preventDefault()` on it — the browser has already committed to scrolling the page. To intercept the wheel event and redirect it to horizontal scroll on the tab container, I had to use `addEventListener` directly with `{ passive: false }`:

```js
el.addEventListener('wheel', handler, { passive: false });
```

This lets me call `preventDefault()` (so the page doesn't scroll) and then manually move `el.scrollLeft` instead.

**Drag scroll**: The drag behavior attaches `mousemove` and `mouseup` listeners on `document` (not the element), so dragging outside the tab strip still works. The calculation is:

```js
scrollLeft = startScroll - (currentX - startX)
```

Standard momentum-based drag.

**Delete button conflict**: The drag listener starts on `mousedown`. But the delete button (`×`) is inside each tab, and clicking it would trigger drag start. I used a `data-action="delete"` attribute on the delete button and skipped drag start if the target matches `[data-action]`:

```js
if (e.target.closest('[data-action]')) return;
```

### Delete button

Each tab has a `×` button that appears on hover (`opacity: 0 → 0.75`). `pointerEvents` is also disabled when not hovered so it's not accidentally clickable. When clicked, it calls `onDelete(tab.id)` which removes the session from localStorage state. If you delete the last session, a new blank one is created automatically.

### Tab labels

Each tab shows two things: an index number (`01 ·`, `02 ·`, etc.) in mono font at smaller size, and the session name in italic serif. The session name defaults to "New chat" and updates to the first 50 characters of the first message sent. That name then sticks — I didn't want session names auto-updating after the first message because it's disorienting to watch a tab label change while you're looking at it.

### Active tab scroll-into-view

When you switch to a session (or a new one is created), the active tab scrolls into view with smooth behavior. This matters when you have many tabs and the active one is off-screen.

---

## Theme toggle

The theme button at the bottom of the rail toggles between `natural` and `mono`. It works by setting `document.documentElement.dataset.theme` and saving to localStorage. The CSS has two `[data-theme]` blocks that redefine all the custom properties. Everything inherits from those, so the whole UI switches with one attribute change.

On initial load, `index.html` has an inline script that reads the saved theme and sets `data-theme` before React loads — this prevents a flash of the wrong theme:

```html
<script>
  try {
    var t = localStorage.getItem('atl_theme');
    if (t) document.documentElement.dataset.theme = JSON.parse(t);
  } catch(e){}
</script>
```

### Why only two themes?

I thought about a full palette picker or more than two themes. Decided against it for two reasons. First, maintaining design token consistency across more than two themes is a lot of work and things drift. Second, having infinite customization options is a different product philosophy than what I want here — I want Atelier to have an identity, not be a blank canvas. Natural and mono are the two moods I actually use.

---

## The pulse dot

The small breathing dot at the very bottom of the rail is purely decorative. It signals "the system is alive" in a quiet way — like a status LED on a piece of equipment. There's no real information in it. I considered connecting it to something meaningful (green when a request is in flight, amber when something is wrong) but that felt like over-engineering something that should be ambient. It just breathes.
