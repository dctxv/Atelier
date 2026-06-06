# Frontend Architecture

*How the frontend is structured and why.*

---

## The core constraint: no build step

The backend is a single `app.py` file. I wanted the frontend to have the same quality — something you can just run, with no compilation, no node_modules, no package.json. No `npm install` before you can see anything.

This meant writing the frontend in JSX but loading it without a bundler. The way that works is:

1. `index.html` loads React, ReactDOM, and Babel from `/lib/` (local files)
2. A small inline script fetches each JSX file in order
3. Each file's source is passed to `Babel.transform()` which compiles it to plain JS in the browser
4. The compiled code is executed with `eval()`

The load sequence is sequential and intentional — each file declares components that the next file depends on. They communicate through the `window` object (e.g. `window.V2Chat = { ChatSurface }`).

```
index.html
  → loads React, ReactDOM, Babel (local)
  → fetches + compiles + evals in order:
      components.jsx   (shared UI primitives)
      shell.jsx        (left rail + tab bar)
      chat.jsx         (chat surface)
      memory.jsx       (memory surface)
      notes.jsx        (notes surface)
      research.jsx     (research surface)
      setup.jsx        (welcome + setup modals)
      app.jsx          (root — renders everything)
```

---

## Why not use a real build tool?

I thought about it. Vite would take about 20 minutes to set up and would make the bundle much smaller (Babel in the browser is 3MB on its own). But it introduces node_modules, a dev server that's separate from the backend, a build step before deployment, and a set of config files I'd have to maintain.

For a personal local tool that I'm the only user of, the tradeoff doesn't make sense. The 3MB Babel download is a one-time hit — the browser caches it. After that, everything loads fast. And not having a build step means the app is genuinely simple: you run `start.ps1` and that's it.

If this ever became something I shipped to other people, I'd add a build step. Until then, no.

---

## Why not use `type="text/babel"`?

Babel standalone supports a `type="text/babel"` attribute on script tags that makes it automatically compile external JSX files. I tried this first. It doesn't work reliably with `src="..."` — it fetches the file but the timing of compilation vs. execution is inconsistent, and there's no guaranteed load order when you have multiple files depending on each other.

The explicit `fetch → Babel.transform → eval` loop solves both problems: I control the load order, and compilation happens synchronously before the next file loads.

---

## Why local libs instead of CDN?

The original implementation used unpkg.com CDN links for React and Babel. This caused a completely white screen because the CDN was unreachable (timeout or block). Since this is a local tool meant to run offline-capable, depending on an external CDN is a bad fit.

The fix was to download the files once and serve them from `/lib/`:

| File | Size | Source |
|---|---|---|
| `react.development.js` | 107 KB | React 18.3.1 dev build |
| `react-dom.development.js` | 1.1 MB | ReactDOM 18.3.1 dev build |
| `babel.min.js` | 3.1 MB | Babel 7.29.0 standalone |

The development builds include full error messages which is useful when things break. If I ever care about load time I'd switch to production builds — that would drop ReactDOM from 1.1MB to around 130KB.

---

## Cache busting

Every JSX file is fetched with a version query string (`?v=20260606`). This is a simple cache-buster. When I change a component, I update the version string in `index.html` and the browser fetches the new version instead of serving from cache.

It's not automatic. I have to remember to bump it. A build tool would handle this automatically with content hashes. For now, manual is fine.

---

## The `window` object as module system

JSX files don't have ES module imports because `eval()`'d code doesn't run in module scope. Instead, each file puts its exports on `window`:

```js
// chat.jsx
window.V2Chat = { ChatSurface };

// app.jsx
const { ChatSurface } = window.V2Chat;
```

This is unusual but it works cleanly for the sequential load model. The alternative would be to compile everything into a single file before eval — but that removes the benefit of keeping files separate and readable.

What I'd do differently if starting over: use ES module `import()` with a small module loader instead of `window`. It would be cleaner and wouldn't pollute the global scope. But `window` works and isn't causing any problems right now.

---

## FastAPI static file serving

The backend serves the entire frontend via FastAPI's `StaticFiles`:

```python
app.mount("/", StaticFiles(directory="static", html=True))
```

The `html=True` flag means requests to `/` serve `index.html`. JSX files, CSS, and lib files are all served from `static/`. There's no separate frontend server. The API (`/api/*`) and the frontend (`/`) run on the same port 8000 from the same process. Simple.
