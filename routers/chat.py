"""Chat SSE proxy — hardened, with parallel gather and typed events.

Architecture (matches the design spec §2):

  [0] CLASSIFY        one pass over user_text → Intent dataclass
  [1] LOCAL-ANSWER?   if single deterministic local query → emit CARD, no LLM
  [2] PARALLEL GATHER asyncio.gather(retrieve, web, weather/stock, local_tools)
  [3] FUSE + BUDGET   assemble context blocks with provenance tags + total cap
  [4] STREAM          resilient SSE: heartbeat, mid-stream degrade, abort persist
  [5] PERSIST         turn + enqueue extract_memory (fires on DONE *and* abort)

Hot-path rules (from docs/shared-core.md):
  1. Nothing blocks a user-facing reply except the model stream.
  3. Cheap model for cheap work (query rewriting only on moderate/hard queries).
  4. Token budgets enforced in code.
  5. One reused httpx.AsyncClient.
  6. One serialized SQLite writer.
"""
from __future__ import annotations

import asyncio
import json
import re
import time as _time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from services import config, http_client, llm, retrieval, search, sessions, skills
from services import math_eval, weather, stock, local_tools
from services import projects as projects_svc
from services.intent import classify, Intent
from workers import jobs

router = APIRouter(prefix="/api")

# ── Config knobs (read from app_config with defaults) ─────────────────────────

_DEFAULTS = {
    "chat.stream_stall_timeout_s":  20,
    "chat.stream_dead_timeout_s":   45,
    "chat.web_results_simple":       5,
    "chat.max_searches_per_turn":    4,
    "chat.rewrite_min_difficulty":  "moderate",
    "chat.total_context_budget":   2400,
    "chat.web_block_budget":       1200,
    "chat.memory_block_budget":     700,
    "chat.skills_block_budget":     400,
    "chat.card_bare_query_only":   True,
}


async def _cfg(key: str):
    val = await config.get_setting(key)
    default = _DEFAULTS.get(key)
    if val is None:
        return default
    if isinstance(default, int):
        try:
            return int(val)
        except (ValueError, TypeError):
            return default
    if isinstance(default, bool):
        return str(val).lower() in ("1", "true", "yes")
    return val


# ── Zone dictionary (shared with local_tools) ─────────────────────────────────
_ZONES: dict[str, str] = {
    "sydney": "Australia/Sydney", "melbourne": "Australia/Melbourne",
    "brisbane": "Australia/Brisbane", "perth": "Australia/Perth",
    "adelaide": "Australia/Adelaide", "darwin": "Australia/Darwin",
    "hobart": "Australia/Hobart", "auckland": "Pacific/Auckland",
    "tokyo": "Asia/Tokyo", "london": "Europe/London",
    "new york": "America/New_York", "los angeles": "America/Los_Angeles",
    "chicago": "America/Chicago", "paris": "Europe/Paris",
    "berlin": "Europe/Berlin", "dubai": "Asia/Dubai",
    "singapore": "Asia/Singapore", "hong kong": "Asia/Hong_Kong",
    "utc": "UTC",
}

DEFAULT_PERSONA = (
    "You are The Atelier, a sophisticated AI workspace assistant. "
    "Provide direct, natural answers. Do not redundantly repeat your conclusions, "
    "equations, or exact phrases across paragraphs. "
    "Use LaTeX formatting like \\( \\) or \\[ \\] for math."
)

# ── SSE helpers ───────────────────────────────────────────────────────────────

def _evt(type_: str, data) -> str:
    """Typed SSE event envelope: {type, data}."""
    return f"data: {json.dumps({'type': type_, 'data': data})}\n\n"


def _legacy_evt(key: str, data) -> str:
    """Legacy envelope (backward compat while frontend migrates)."""
    return f"data: {json.dumps({key: data})}\n\n"


def _token_evt(delta: str) -> str:
    """Standard OpenAI-format token chunk (kept for frontend compat)."""
    return f"data: {json.dumps({'choices': [{'delta': {'content': delta}}]})}\n\n"


# ── Clock card (unchanged logic, extended with tz_abbrev from intent) ─────────

def _clock_data(text: str, tz_abbrev: str | None = None) -> dict | None:
    q = text.lower()
    zone_name = tz_abbrev
    location = None

    if not zone_name:
        matched_key = next((k for k in _ZONES if k in q), None)
        if matched_key:
            zone_name = _ZONES[matched_key]
            location = matched_key.title()

    if zone_name:
        try:
            tz = ZoneInfo(zone_name)
            now = datetime.now(tz)
            if not location:
                location = zone_name.split("/")[-1].replace("_", " ")
        except Exception:
            now = datetime.now().astimezone()
            location = "Local"
    else:
        now = datetime.now().astimezone()
        offset_secs = now.utcoffset().total_seconds() if now.utcoffset() else 0
        h, m = divmod(int(abs(offset_secs)) // 60, 60)
        sign = "+" if offset_secs >= 0 else "-"
        location = f"UTC{sign}{h}" if m == 0 else f"UTC{sign}{h}:{m:02d}"

    offset_secs = now.utcoffset().total_seconds() if now.utcoffset() else 0
    offset_h = int(offset_secs // 3600)
    offset_str = f"({'+' if offset_h >= 0 else ''}{offset_h:02d})"
    return {
        "time": now.strftime("%I:%M%p").lstrip("0"),
        "date": now.strftime(f"%A, %B %d, %Y {offset_str}"),
        "location": location,
        "iso": now.isoformat(),
    }


# ── Context budget assembly ───────────────────────────────────────────────────

_CHARS_PER_TOKEN = 4


def _tok(s: str) -> int:
    return max(1, len(s) // _CHARS_PER_TOKEN)


def assemble_context(blocks: list[tuple[str, str]], total_budget: int) -> str:
    """
    blocks: list of (priority_key, text)
      priority_key: "persona"|"computed"|"live"|"weather"|"stock"|"web"|"memory"|"skills"

    Returns combined context string respecting the total_budget.
    Priority order: persona > computed > weather/stock > web > memory > skills
    """
    PRIORITY = ["persona", "manifest", "wholefile", "computed", "weather", "stock", "live", "web", "memory", "docs", "skills"]

    sorted_blocks = sorted(blocks, key=lambda x: PRIORITY.index(x[0]) if x[0] in PRIORITY else 99)

    result_parts: list[str] = []
    used = 0
    for key, text in sorted_blocks:
        if not text:
            continue
        cost = _tok(text)
        if used + cost > total_budget and key not in ("persona", "computed"):
            # Try to include a truncated version for lower-priority blocks
            remaining = (total_budget - used) * _CHARS_PER_TOKEN
            if remaining > 200 and key not in ("persona", "computed"):
                text = text[:remaining] + "\n[… truncated to fit context budget]"
                cost = _tok(text)
            else:
                continue  # skip entirely
        result_parts.append(text)
        used += cost

    return "\n\n".join(result_parts)


# ── Query rewriting ───────────────────────────────────────────────────────────

async def _rewrite_query(user_text: str, history: list[dict], difficulty: str) -> list[str]:
    """Use cheap model to rewrite conversational text into clean search queries."""
    k = 2 if difficulty == "moderate" else 3
    # Include last 2 turns for context
    context_turns = history[-4:] if len(history) >= 4 else history
    ctx_lines = []
    for m in context_turns:
        role = "User" if m.get("role") == "user" else "Assistant"
        content = (m.get("content") or "")[:200]
        ctx_lines.append(f"{role}: {content}")

    ctx_str = "\n".join(ctx_lines)
    prompt = (
        f"Rewrite the user's request into {k} focused web-search queries. "
        f"Resolve pronouns and references using the conversation context. "
        f"Each query should be keyword-style, not a question. "
        f"Return ONLY a JSON array of strings, no other text.\n\n"
        f"Conversation context:\n{ctx_str}\n\n"
        f"User request: {user_text}"
    )
    try:
        raw = await llm.cheap(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200,
            task="query_rewrite",
        )
        # Parse the JSON array
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw).rstrip("`").strip()
        queries = json.loads(raw)
        if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
            return [q.strip() for q in queries if q.strip()][:k]
    except Exception:
        pass
    return [user_text]  # fallback to raw text


# ── Parallel gather legs ──────────────────────────────────────────────────────

async def _noop():
    return None


async def _fetch_project_manifest(project_id: str) -> tuple[str, list, dict | None]:
    """Parallel gather leg: fetch project record + build manifest."""
    try:
        proj = await projects_svc.get(project_id)
        if not proj:
            return "", [], None
        manifest_text, docs = await projects_svc.build_manifest(project_id)
        return manifest_text, docs, proj
    except Exception:
        return "", [], None


async def _run_web_search(
    user_text: str,
    queries: list[str],
    max_results: int,
    max_turns: int,
) -> dict | None:
    """Run 1..K search queries concurrently, fuse results."""
    try:
        tasks = [
            search.search(q, max_results=max_results, top_k=3, want_content=True)
            for q in queries[:max_turns]
        ]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        all_results = []
        providers_used = []
        as_of = None
        from_cache = True

        for r in results_list:
            if isinstance(r, Exception):
                continue
            all_results.extend(r.results)
            providers_used.extend(r.providers_used)
            if r.as_of:
                as_of = max(as_of or 0, r.as_of)
            if not r.from_cache:
                from_cache = False

        # Deduplicate by URL
        seen_urls: set[str] = set()
        deduped = []
        for res in all_results:
            if res.url not in seen_urls:
                seen_urls.add(res.url)
                deduped.append(res)

        if not deduped:
            return None

        return {
            "results": deduped,
            "providers_used": list(set(providers_used)),
            "as_of": as_of,
            "from_cache": from_cache,
            "queries": queries,
        }
    except Exception as e:
        return {"error": str(e), "degraded": True}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _last_user_text(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return m.get("content") or ""
    return ""


def _inject_front(messages: list[dict], block: str) -> list[dict]:
    """Prepend block to system message (unchanged from original)."""
    if not block:
        return messages
    if messages and messages[0].get("role") == "system":
        return [{**messages[0], "content": block + "\n\n" + messages[0]["content"]}] + messages[1:]
    return [{"role": "system", "content": block}] + messages


# ── Main endpoint ─────────────────────────────────────────────────────────────

@router.post("/chat/stream")
async def chat_stream(request: Request):
    body = await request.json()
    ep = await config.active_endpoint_raw()
    if not ep:
        raise HTTPException(400, "No endpoint configured. Type /setup to connect.")
    model = body.get("model") or await config.get_setting("active_model")
    if not model:
        raise HTTPException(400, "No model selected. Open the model picker to choose one.")

    messages = list(body.get("messages", []))
    user_text = _last_user_text(messages)
    session_id = body.get("session_id")
    web_search_enabled = bool(body.get("web_search"))
    project_id = body.get("project_id") or None

    # Load config knobs
    total_budget = int(await _cfg("chat.total_context_budget"))
    web_budget   = int(await _cfg("chat.web_block_budget"))
    mem_budget   = int(await _cfg("chat.memory_block_budget"))
    skill_budget = int(await _cfg("chat.skills_block_budget"))
    max_searches = int(await _cfg("chat.max_searches_per_turn"))
    rewrite_min  = await _cfg("chat.rewrite_min_difficulty")
    web_results  = int(await _cfg("chat.web_results_simple"))
    card_bare    = await _cfg("chat.card_bare_query_only")
    stall_t      = int(await _cfg("chat.stream_stall_timeout_s"))
    dead_t       = int(await _cfg("chat.stream_dead_timeout_s"))

    # [0] CLASSIFY
    intent = classify(user_text) if user_text else Intent()

    # ── Chat-only short-circuit ───────────────────────────────────────────────
    if intent.is_chat_only:
        persona = await config.get_setting("system_prompt") or DEFAULT_PERSONA
        messages = _inject_front(messages, persona)
        payload = {"model": model, "messages": messages, "stream": True}
        for k in ("temperature", "max_tokens"):
            if k in body:
                payload[k] = body[k]

        async def generate_chat_only():
            assistant_chunks: list[str] = []
            try:
                async with http_client.client().stream(
                    "POST", f"{ep['url']}/chat/completions", json=payload,
                    headers=config.headers(ep), timeout=180,
                ) as resp:
                    if resp.status_code != 200:
                        err = await resp.aread()
                        yield _evt("error", {"code": "provider_error", "message": err.decode()[:300]})
                        return
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        yield f"{line}\n\n"
                        if line.startswith("data: "):
                            ds = line[6:].strip()
                            if ds and ds != "[DONE]":
                                try:
                                    delta = json.loads(ds)["choices"][0]["delta"].get("content")
                                    if delta:
                                        assistant_chunks.append(delta)
                                except Exception:
                                    pass
            except Exception as e:
                yield _evt("error", {"code": "stream_error", "message": str(e)})
            finally:
                yield "data: [DONE]\n\n"
                assistant_text = "".join(assistant_chunks).strip()
                if session_id and user_text:
                    await sessions.add_message(session_id, "user", user_text, model)
                if session_id and assistant_text:
                    await sessions.add_message(session_id, "assistant", assistant_text, model)
                if user_text or assistant_text:
                    await jobs.enqueue("extract_memory", {
                        "user_text": user_text, "assistant_text": assistant_text,
                        "source_kind": "chat", "source_id": session_id,
                        "project_id": project_id,
                    })

        return StreamingResponse(
            generate_chat_only(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
        )

    # [1] LOCAL-ANSWER CARD CHECK
    clock_data = None
    card_data = None

    if intent.time_query:
        clock_data = _clock_data(user_text, intent.tz_abbrev)

    # Local-answer card check (no LLM). Math/unit are pre-flagged by the
    # classifier; the local_tools family (date math, base/hash/color, timezone
    # diff, tip/split) is pattern-matched directly — those patterns are specific
    # enough to attempt on any short, non-web query the classifier didn't claim.
    if not clock_data and card_bare and not intent.needs_web:
        # Classifier-flagged exact math / unit conversion.
        if intent.is_bare_local and (intent.math_expr or intent.unit_conv):
            result = math_eval.evaluate(user_text)
            if result:
                card_data = {
                    "kind": "unit" if intent.unit_conv else "math",
                    "expr": intent.math_expr or user_text,
                    "result": result,
                }
        # Other deterministic local tools (date, base, hash, color, tip/split).
        # Runs as a fallback when no math/unit card was produced — its patterns
        # are specific, so it's safe on any short non-web query (e.g. a "% tip"
        # query the math branch couldn't evaluate).
        if (not card_data and not intent.stock_ticker and intent.weather_loc is None
                and len(user_text.split()) <= 14):
            local_result = local_tools.try_local(user_text)
            if local_result:
                card_data = local_result

    # Stock and weather are NOT pure-local cards (they need I/O) — handled in gather below
    # but they CAN become cards after the gather if is_bare_local and the data looks clean.

    # [2] PARALLEL GATHER
    # Prepare search queries (with optional rewriting for moderate/hard)
    search_queries: list[str] = [user_text]
    do_search = (web_search_enabled and not clock_data and not card_data
                 and intent.needs_web)

    suggest_web = (not web_search_enabled and not clock_data and not card_data
                   and intent.needs_web and intent.web_difficulty in ("moderate", "hard"))

    # Query rewriting (async, before gather)
    if do_search and intent.web_difficulty in (rewrite_min, "hard") and intent.web_difficulty != "simple":
        try:
            rewritten = await _rewrite_query(user_text, messages, intent.web_difficulty)
            if rewritten:
                search_queries = rewritten
        except Exception:
            pass  # fallback to raw text

    # Scale result count by difficulty
    _results_by_diff = {"simple": web_results, "moderate": web_results, "hard": web_results}
    results_per_query = _results_by_diff.get(intent.web_difficulty, web_results)

    gather_results = await asyncio.gather(
        # Memory + docs (scoped to project when inside one)
        retrieval.retrieve(user_text, budget_tokens=mem_budget, project_id=project_id)
            if user_text and not clock_data and not card_data else _noop(),
        # Web search
        _run_web_search(user_text, search_queries, results_per_query, max_searches) if do_search else _noop(),
        # Weather
        weather.get_weather(intent.weather_loc) if intent.weather_loc else _noop(),
        # Stock
        stock.get_stock(intent.stock_ticker) if intent.stock_ticker else _noop(),
        # Project manifest (Tier 1) — runs in parallel, librarian runs after
        _fetch_project_manifest(project_id)
            if project_id and not clock_data and not card_data else _noop(),
        return_exceptions=True,
    )

    atoms_result, web_result, weather_result, stock_result, manifest_result = gather_results

    # Safe-unwrap (return_exceptions=True means failed legs are Exceptions)
    atoms    = atoms_result if isinstance(atoms_result, list) else []
    web_resp = web_result   if isinstance(web_result, dict) else None
    w_data   = weather_result if isinstance(weather_result, dict) and not isinstance(weather_result, Exception) else None
    s_data   = stock_result   if isinstance(stock_result, dict) and not isinstance(stock_result, Exception) else None

    # Unpack project manifest (Tier 1)
    project_manifest_text = ""
    proj_docs: list = []
    project_obj: dict | None = None
    if isinstance(manifest_result, tuple) and not isinstance(manifest_result, Exception):
        project_manifest_text, proj_docs, project_obj = manifest_result

    # ── Tier 3: librarian gate (sequential — needs retrieved chunks) ──────────
    project_wholefile = ""
    if project_id and project_obj and not clock_data and not card_data:
        doc_atoms = [a for a in atoms if a.get("source_type") == "document"]
        top_chunk_score = doc_atoms[0]["score"] if doc_atoms else None
        gate = projects_svc.should_call_librarian(
            user_text, proj_docs, top_chunk_score,
            small_files=3, small_tokens=6000,
        )
        wholefile_budget = 2000
        if gate == "dump":
            ready_ids = [d["id"] for d in proj_docs if d.get("status") == "ready"]
            project_wholefile = await projects_svc.load_full_files(ready_ids, wholefile_budget)
        elif gate == "librarian":
            selected_ids = await projects_svc.run_librarian(
                user_text, project_manifest_text, atoms, proj_docs
            )
            if selected_ids:
                project_wholefile = await projects_svc.load_full_files(selected_ids, wholefile_budget)

    # Check if stock/weather is a bare card
    if not card_data and intent.is_bare_local:
        if intent.stock_ticker and s_data and not s_data.get("error"):
            card_data = {"kind": "stock", **s_data}
        elif intent.weather_loc is not None and w_data and not w_data.get("error"):
            card_data = {"kind": "weather", **w_data}

    # [3] FUSE + BUDGET — assemble context blocks with provenance tags
    # Tier 0: persona — project instructions override global system_prompt
    if project_obj and project_obj.get("instructions"):
        persona = project_obj["instructions"]
    else:
        persona = await config.get_setting("system_prompt") or DEFAULT_PERSONA
    context_blocks: list[tuple[str, str]] = [("persona", persona)]

    # Tier 1: project manifest (file index)
    if project_manifest_text:
        context_blocks.append(("manifest", project_manifest_text))

    # Tier 3: whole-file contents (loaded on demand by librarian)
    if project_wholefile:
        context_blocks.append(("wholefile",
            "[FULL FILE CONTENTS — loaded because the question needs them]\n"
            + project_wholefile))

    # Math/unit computed result (not a card — has substantive remainder)
    if not card_data:
        if intent.math_expr or intent.unit_conv:
            computed = math_eval.evaluate(user_text)
            if computed:
                context_blocks.append((
                    "computed",
                    f"[COMPUTED — exact, trust completely] {computed}",
                ))

    # Weather context block (when not a bare card)
    if w_data and not w_data.get("error") and not card_data:
        now_str = datetime.now().strftime("%H:%M")
        context_blocks.append((
            "weather",
            f"[WEATHER — fetched {now_str}, OpenWeatherMap] "
            f"Current weather for {w_data.get('location', intent.weather_loc)}:\n"
            f"Temperature: {w_data.get('temperature_celsius')}°C, "
            f"Feels like: {w_data.get('feels_like_celsius')}°C, "
            f"Condition: {w_data.get('condition')}, "
            f"Humidity: {w_data.get('humidity_percent')}%, "
            f"Wind: {w_data.get('wind_speed_m_s')} m/s\n"
            f"Answer directly using this data.",
        ))

    # Stock context block (when not a bare card)
    if s_data and not s_data.get("error") and not card_data:
        now_str = datetime.now().strftime("%H:%M")
        context_blocks.append((
            "stock",
            f"[STOCK — fetched {now_str}, Finnhub] "
            f"Real-time quote for {s_data.get('symbol')}:\n"
            f"Price: ${s_data.get('current_price')}, "
            f"Change: {s_data.get('change')} ({s_data.get('percent_change')}%), "
            f"Day range: ${s_data.get('low_day')}–${s_data.get('high_day')}\n"
            f"Answer directly using this data.",
        ))

    # Web search context block
    web_trace = None
    web_degraded = False
    if web_resp:
        if web_resp.get("degraded"):
            web_degraded = True
            context_blocks.append((
                "web",
                "[WEB SEARCH] No live results were available. Answer from your "
                "training knowledge and explicitly say so if the question needs current information.",
            ))
        elif web_resp.get("results"):
            as_of = web_resp.get("as_of")
            as_of_str = ""
            if as_of:
                as_of_str = f" fetched {datetime.fromtimestamp(as_of, timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
            lines = [
                f"[LIVE WEB —{as_of_str}] You have live web results below. "
                "Answer directly from them. Do NOT say you lack web access, have a "
                "knowledge cutoff, or cannot browse — you are looking at real search "
                "results right now. Cite the source URLs inline when making factual claims."
            ]
            # Build provenance instruction
            lines.append(
                "\nInstruction: LIVE WEB values are authoritative and current. "
                "Do not override them with training data. Cite URLs."
            )
            total_web_chars = web_budget * _CHARS_PER_TOKEN
            used_chars = sum(len(l) for l in lines)
            for r in web_resp["results"]:
                body_text = (r.content if hasattr(r, "content") else r.get("content", "")) or \
                            (r.snippet if hasattr(r, "snippet") else r.get("snippet", ""))
                body_text = (body_text or "")[:600]
                pub = ""
                published_at = r.published_at if hasattr(r, "published_at") else r.get("published_at")
                if published_at:
                    try:
                        pub = f" [{datetime.fromtimestamp(published_at).strftime('%Y-%m-%d')}]"
                    except Exception:
                        pass
                url = r.url if hasattr(r, "url") else r.get("url", "")
                title = r.title if hasattr(r, "title") else r.get("title", url)
                entry = f"- {title} ({url}){pub}\n  {body_text}"
                if used_chars + len(entry) > total_web_chars:
                    break
                lines.append(entry)
                used_chars += len(entry)

            context_blocks.append(("web", "\n".join(lines)))
            web_trace = {
                "query": search_queries[0] if len(search_queries) == 1 else user_text,
                "queries": search_queries,
                "providers": web_resp.get("providers_used", []),
                "from_cache": web_resp.get("from_cache", False),
                "as_of": web_resp.get("as_of"),
                "results": [
                    {
                        "title": r.title if hasattr(r, "title") else r.get("title", ""),
                        "url": r.url if hasattr(r, "url") else r.get("url", ""),
                        "published_at": r.published_at if hasattr(r, "published_at") else r.get("published_at"),
                        "stale": r.stale if hasattr(r, "stale") else r.get("stale", False),
                    }
                    for r in web_resp["results"]
                ],
            }

    # Memory + docs
    mem_block = retrieval.format_block(atoms)
    doc_filenames = retrieval.doc_sources(atoms)
    if mem_block:
        # Add provenance instruction to memory block
        mem_with_instruction = mem_block + (
            "\n[MEMORY values reflect what you know about the user. "
            "Use them naturally — don't list them verbatim. "
            "If COMPUTED or LIVE WEB values conflict with MEMORY, trust the newer source.]"
        )
        context_blocks.append(("memory", mem_with_instruction))

    # Skills
    enabled = await skills.enabled_skills()
    enabled = [s for s in enabled if s.get("prompt") or s.get("description")]
    if enabled:
        skills_ctx = "You have these skills and capabilities available:\n" + "\n".join(
            f"- {s['name']}: {s.get('prompt') or s.get('description', '')}" for s in enabled
        )
        context_blocks.append(("skills", skills_ctx))

    # Global provenance instruction (appended to computed/live blocks)
    if any(k in ("computed", "weather", "stock", "web") for k, _ in context_blocks):
        context_blocks.append((
            "computed",
            "PROVENANCE RULE: "
            "COMPUTED values are exact — do not round or approximate them. "
            "LIVE WEB / WEATHER / STOCK values are current fetched data — cite them as such. "
            "MEMORY values are things you know about the user from previous conversations. "
            "If you state a current fact not present in the above context, flag it as "
            "your own estimate based on training knowledge.",
        ))

    # Provenance summary — what grounded the answer (rendered as chips, §7.3).
    mem_atoms = [a for a in atoms if a.get("source_type") != "document"]
    prov_sources: list[dict] = []
    seen_src: set = set()
    for a in atoms:
        sk, sid = a.get("source_kind"), a.get("source_id")
        if sk in ("note", "research", "document") and sid and (sk, sid) not in seen_src:
            seen_src.add((sk, sid))
            label = a.get("filename") if sk == "document" else (a.get("text") or "")[:48]
            prov_sources.append({"kind": sk, "id": sid, "label": label})
    provenance = {
        "computed": bool(((intent.math_expr or intent.unit_conv) and not card_data)
                         or w_data or s_data),
        "web": len(web_trace["results"]) if web_trace else 0,
        "memory": len(mem_atoms),
        "docs": doc_filenames,
        "sources": prov_sources[:6],
    }

    # Assemble with total budget
    system_context = assemble_context(context_blocks, total_budget)
    messages = _inject_front(messages, system_context)

    payload = {"model": model, "messages": messages, "stream": True}
    for k in ("temperature", "max_tokens"):
        if k in body:
            payload[k] = body[k]

    # Persist user turn before streaming
    if session_id and user_text:
        await sessions.add_message(session_id, "user", user_text, model)

    # [4] STREAM — resilient SSE generator
    async def generate():
        assistant_chunks: list[str] = []
        first_token_received = False
        last_byte_time = _time.monotonic()

        try:
            # [1] LOCAL-ANSWER CARDS — no LLM call
            if clock_data:
                yield _legacy_evt("atelier_clock", clock_data)
                yield _evt("clock", clock_data)
                yield "data: [DONE]\n\n"
                return

            if card_data:
                yield _evt("card", card_data)
                yield "data: [DONE]\n\n"
                return

            # Suggest web search (proactive freshness)
            if suggest_web:
                yield _evt("status", "suggest_web")

            # Emit doc chips
            if doc_filenames:
                yield _legacy_evt("atelier_docs", doc_filenames)
                yield _evt("docs", doc_filenames)

            # Emit search trace (or degraded notice)
            if web_trace:
                yield _legacy_evt("atelier_search", web_trace)
                yield _evt("search", {**web_trace, "degraded": False})
            elif web_degraded:
                yield _evt("search", {"degraded": True, "query": user_text})

            # Provenance chips — the answer's grounding made legible (§7.3)
            if (provenance["computed"] or provenance["web"]
                    or provenance["memory"] or provenance["docs"]):
                yield _evt("provenance", provenance)

            # Status line hint to frontend
            if web_trace:
                yield _evt("status", "searching")
            elif atoms:
                yield _evt("status", "recalling")

            # Stream from model
            async with http_client.client().stream(
                "POST", f"{ep['url']}/chat/completions", json=payload,
                headers=config.headers(ep), timeout=180,
            ) as resp:
                if resp.status_code != 200:
                    err = await resp.aread()
                    code = "auth" if resp.status_code in (401, 403) else "provider_5xx"
                    yield _evt("error", {"code": code, "message": err.decode()[:300]})
                    return

                # A stalled upstream blocks aiter_lines() indefinitely, so timing
                # checks placed *inside* the for-loop never fire. Instead a pump
                # task owns the read and feeds a queue; the consumer waits on the
                # queue with a timeout, so true stalls are detectable.
                line_q: asyncio.Queue = asyncio.Queue()

                async def _pump():
                    try:
                        async for ln in resp.aiter_lines():
                            await line_q.put(("line", ln))
                    except Exception as ex:  # noqa: BLE001
                        await line_q.put(("error", str(ex)))
                    finally:
                        await line_q.put(("end", None))

                pump_task = asyncio.create_task(_pump())
                stalled_announced = False
                try:
                    while True:
                        try:
                            kind, val = await asyncio.wait_for(line_q.get(), timeout=stall_t)
                        except asyncio.TimeoutError:
                            if _time.monotonic() - last_byte_time > dead_t:
                                yield _evt("status", "interrupted")
                                yield _evt("error", {"code": "stream_timeout",
                                                     "message": "Stream timed out"})
                                return
                            if not stalled_announced:
                                stalled_announced = True
                                yield _evt("status", "stalled")
                            continue

                        if kind == "end":
                            break
                        if kind == "error":
                            raise RuntimeError(val)

                        line = val
                        if not line:
                            continue

                        last_byte_time = _time.monotonic()
                        stalled_announced = False
                        yield f"{line}\n\n"  # pass-through for frontend token accumulation

                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str and data_str != "[DONE]":
                                try:
                                    delta = json.loads(data_str)["choices"][0]["delta"].get("content")
                                    if delta:
                                        assistant_chunks.append(delta)
                                        if not first_token_received:
                                            first_token_received = True
                                            yield _evt("status", "streaming")
                                except Exception:
                                    pass
                finally:
                    pump_task.cancel()

        except asyncio.CancelledError:
            # Client disconnected — still persist
            pass
        except Exception as e:
            if assistant_chunks:
                # Mid-stream failure after some tokens — degrade gracefully
                yield _evt("status", "interrupted")
            else:
                yield _evt("error", {"code": "stream_error", "message": str(e)})
        finally:
            yield "data: [DONE]\n\n"
            # [5] PERSIST — always, regardless of exit path
            assistant_text = "".join(assistant_chunks).strip()
            if session_id and assistant_text:
                await sessions.add_message(session_id, "assistant", assistant_text, model)
            if user_text or assistant_text:
                await jobs.enqueue("extract_memory", {
                    "user_text": user_text,
                    "assistant_text": assistant_text,
                    "source_kind": "chat",
                    "source_id": session_id,
                    "project_id": project_id,
                })

    return StreamingResponse(
        generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
