# Setup Flow

*The welcome modal and API configuration wizard.*

---

## First run experience

The first time you open Atelier, nothing is configured. No endpoints, no model. Without a model you can't chat. The first-run experience needs to make that setup fast and clear without being condescending.

The `atl_welcomed` key in localStorage tracks whether you've seen the welcome screen. If it's not set, the welcome modal appears. Once you dismiss it (either by setting up or skipping), it's set and never shown again.

---

## Welcome modal

The welcome modal is the first thing a new user sees. It has:

1. The "A" monogram icon (same as the nav rail)
2. A heading: "Welcome to Atelier"
3. A one-paragraph explanation of what it is
4. Two buttons: "Set up a model" and "Skip for now — I'll type /setup later"

The copy is intentional. "Connect any model you already have access to" tells you immediately that this isn't a model you pay for here — it's a surface for models you already have elsewhere. "Your personal AI workspace" sets the tone. Short, not a tutorial.

The skip button's label ("I'll type /setup later") teaches the slash command in the act of dismissing the modal. That way even if you skip, you know how to get back to setup.

### What I considered for the welcome modal

I thought about making the welcome modal more elaborate — a multi-step onboarding tour with tooltips pointing to features. Decided against it. A tour is condescending for a personal tool. If I'm setting this up for myself, I know what I'm doing. The modal should get out of the way fast.

I also thought about skipping the welcome modal entirely and just dropping you into the setup flow directly on first run. The reason I kept it as a separate step: sometimes you might open the app just to look at it without being ready to set up an API key. The skip option respects that.

---

## Setup modal — 4 steps

### Step 1: Connect your AI

A URL field, an API key field, and a name field. Above them, preset buttons for common providers:

| Preset | URL |
|---|---|
| OpenRouter | `https://openrouter.ai/api/v1` |
| OpenAI | `https://api.openai.com/v1` |
| Ollama | `http://localhost:11434` |
| Anthropic | `https://api.anthropic.com/v1` |
| LM Studio | `http://localhost:1234` |

Clicking a preset fills the URL field. This handles the most common case — people usually know which provider they're using but don't have the base URL memorized.

Pressing "Connect & fetch models →" calls `POST /api/models/probe` with the URL and API key. The backend tries to reach the endpoint and returns the list of available models. If it can't connect, the error message is shown inline (not in a toast, not in a dialog — right below the button).

**What I considered**: I thought about auto-detecting the provider type from the URL and pre-filling some fields (e.g. if you type `openrouter.ai` anywhere, auto-select OpenRouter preset). Decided it was too clever. Manual preset selection is just as fast and less surprising.

I also considered adding a "Test connection" button separate from the probe — so you could verify connectivity without moving to step 2. The probe already does this, so a separate test button would be redundant.

### Step 2: Select default model

After a successful probe, you see a searchable list of the models returned by the endpoint. Up to 280px tall with internal scroll for long lists (OpenRouter returns 200+ models).

Each row shows the short model name (after the last `/`) in italic serif, and the full ID in mono at smaller size on the right. Clicking a model immediately saves it — no confirmation step. The save flow:

1. `POST /api/endpoints` — creates the endpoint record
2. `POST /api/endpoints/{id}/activate` — sets it as active
3. `PATCH /api/config` — sets the active model
4. Auto-advance to step 3

**What I considered**: I thought about letting you pick multiple models and switch between them later, with step 2 showing a "set as default" button per model. Decided this was scope creep. You can always change the model in the composer picker. The setup flow should just get you to a working state, not be a full configuration panel.

### Step 3: Background model

After choosing a primary model, you're asked to choose a cheaper, faster model for background work — memory extraction, mail categorisation, flashcard generation. These are cheap-work tasks that should never run on the same expensive model as the actual conversation.

The UI is the same searchable model list from step 2 (same endpoint, same model set). There are two ways to proceed:

- **Click a model row** — sets it as `cheap_model` via `PATCH /api/config` and advances to step 4
- **"Use same model" button** — explicitly sets `cheap_model` to the same model chosen in step 2 (not null — an explicit value)

A ← Back button returns to step 2 if you want to change your primary model.

The `cheap_model` is exposed in `GET /api/config` and read by `services/llm.py` `cheap()`. Before this step existed, `cheap()` would silently fall back to `active_model` because `cheap_model` was never set — so every background task ran on the main model. That was a direct cost leak, invisible because nothing surfaced it.

**What I considered**: I thought about adding a persistent "Background model" setting in a settings panel rather than in the wizard. Decided the wizard is the right place — it's the moment you're thinking about models anyway, and re-running `/setup` reaches it again. A separate settings page would be justified if there were many more settings to expose.

I also considered auto-suggesting a smaller model (e.g. the smallest model in the list by name heuristic). Too clever. The user knows their endpoint — if it's OpenRouter they know which models are fast and cheap. Showing the full list with a filter is better than guessing.

### Step 4: Ready

A check mark, a confirmation message ("Model saved. Ready to chat."), and then automatic dismissal after 1.4 seconds. You land on the chat surface.

The auto-dismiss is intentional — there's nothing to do on step 4. Having a "Start chatting →" button would make you click a button just to close a modal. The brief pause with a success state feels better than just snapping shut.

---

## Re-opening setup

After first run, you can get back to the setup modal via the command palette — type `/` in the composer, then `/setup` to filter down to the "Set up model / endpoint" command, and press Enter. Or type `/setup search`, `/setup weather`, `/setup stock` to reach the individual provider modals.

The setup modal is functionally identical whether opened fresh or re-opened. Walking through it again replaces the active endpoint and model. The welcome modal does not reappear — that's a one-time thing.

I chose not to add a dedicated "Settings" page for endpoint/model management. The setup flow handles the initial configuration and the model picker in the composer handles day-to-day model switching. A full settings page would be the right call if there were more things to configure (notifications, keyboard shortcuts, etc.), but adding it now for just endpoint management would feel overbuilt.

---

## What resets when you "start fresh"

If you want to start completely fresh (no history, no sessions, no saved configuration), you clear localStorage in the browser and the backend data files reset. The welcome modal reappears on next load because `atl_welcomed` is gone. This is how the "reset account" flow was handled — no special UI, just clearing the data.

I considered building an explicit "Reset" button inside settings. Decided to leave it as a manual localStorage + data file clear for now. The risk of an accidental reset via a UI button felt higher than the inconvenience of doing it manually.
