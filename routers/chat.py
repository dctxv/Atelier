"""Chat SSE proxy with skill + memory injection (Part 2.1).

On each user message we call retrieve() and prepend a compact MEMORY block to
the system prompt — reusing the exact mechanism that already injects skills.
Nothing blocks the stream except the model itself (hot-path rule 1): retrieval
is a fast local read, and extraction is enqueued as a background job AFTER the
reply completes.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from services import config, http_client, retrieval, search, sessions, skills, math_eval, weather, stock
from workers import jobs

router = APIRouter(prefix="/api")

MEMORY_BUDGET_TOKENS = 700
WEB_RESULTS = 5
WEB_TOP_K = 3

_WEATHER_Q = re.compile(
    r"\b(weather|temperature|forecast|how (hot|cold) is it)\s*(in|for|at)?\s*([a-zA-Z\s,]+)\b", re.I
)

_STOCK_Q = re.compile(
    r"\b(stock|price|quote|shares?)\s*(of|for)?\s*([A-Z]{1,5})\b", re.I
)

# ── Queries that are definitely time lookups ───────────────────────────────────
_TIME_Q = re.compile(
    r"\b(what(?:'s| is) (the )?time|current time|time (now|in|at)|"
    r"what time is it|clock in|date (today|now|in)|today'?s date)\b", re.I)

_ZONES = {
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

# Signals that a query actually benefits from a live web search.
_SEARCH_SIGNALS = re.compile(
    r"\b(today|tonight|right now|just now|breaking|latest|current(ly)?|"
    r"live|update[sd]?|recent(ly)?|this (morning|week|month|year)|"
    r"news|price[sd]?|stock|weather|score[sd]?|standings?|results?|"
    r"who (won|is winning)|announce[ds]?|launch(ed)?|release[ds]?|"
    r"died?|killed|attack(ed)?|strike[sd]?|election|forecast|"
    r"how (do|does|to)|what is|explain|definition|meaning of|vs\.?|"
    r"compare|review|recommend|best|top \d|20[2-9]\d)\b", re.I)

# Short conversational messages that are never worth searching.
_CHAT_ONLY = re.compile(
    r"^(hey|hi|hello|sup|yo|thanks?|thank you|ok|okay|sure|cool|got it|"
    r"nice|great|lol|haha|wow|yes|no|nope|yep|please|sorry|excuse me|"
    r"good morning|good night|good evening|how are you|what'?s up)[!?.,\s]*$", re.I)


def _needs_web(text: str) -> bool:
    """Return True only when a live web lookup is likely to improve the reply."""
    t = (text or "").strip()
    if not t or len(t) < 6:
        return False
    if _CHAT_ONLY.match(t):
        return False
    # Time lookups are handled separately with the system clock — no web needed.
    if _TIME_Q.search(t):
        return False
    return bool(_SEARCH_SIGNALS.search(t))


def _clock_data(text: str) -> dict | None:
    """If the query asks for the current time/date, return structured clock data.

    Emitted as atelier_clock over SSE — the frontend renders the card.
    Nothing is injected into the model prompt; the card is the answer.
    """
    if not _TIME_Q.search(text):
        return None
    q = text.lower()
    matched_key = next((k for k in _ZONES if k in q), None)

    if matched_key:
        zone_name = _ZONES[matched_key]
        location = matched_key.title()
        try:
            tz = ZoneInfo(zone_name)
            now = datetime.now(tz)
        except Exception:
            now = datetime.now().astimezone()
            location = now.strftime("%Z") or "Local"
    else:
        # No city specified — use the server's actual local time, never UTC.
        now = datetime.now().astimezone()
        # Derive a clean label from the UTC offset (avoids Windows' long names).
        offset_secs = now.utcoffset().total_seconds() if now.utcoffset() else 0
        h, m = divmod(int(abs(offset_secs)) // 60, 60)
        sign = "+" if offset_secs >= 0 else "-"
        location = f"UTC{sign}{h}" if m == 0 else f"UTC{sign}{h}:{m:02d}"
    # offset like (+10) or (-03)
    offset_secs = now.utcoffset().total_seconds() if now.utcoffset() else 0
    offset_h = int(offset_secs // 3600)
    offset_str = f"({'+' if offset_h >= 0 else ''}{offset_h:02d})"
    return {
        "time": now.strftime("%I:%M%p").lstrip("0"),          # e.g. "2:52PM"
        "date": now.strftime(f"%A, %B, %d, %Y {offset_str}"), # e.g. "Saturday, June, 06, 2026 (+10)"
        "location": location,
        "iso": now.isoformat(),
    }


def _last_user_text(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return m.get("content") or ""
    return ""


def _inject(messages: list[dict], block: str) -> list[dict]:
    if not block:
        return messages
    if messages and messages[0].get("role") == "system":
        messages = [{**messages[0], "content": block + "\n\n" + messages[0]["content"]}] + messages[1:]
    else:
        messages = [{"role": "system", "content": block}] + messages
    return messages


DEFAULT_PERSONA = (
    "You are The Atelier, a sophisticated AI workspace assistant. "
    "Provide direct, natural answers. Do not redundantly repeat your conclusions, equations, or exact phrases across paragraphs. "
    "Use LaTeX formatting like \\( \\) or \\[ \\] for math."
)


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

    persona = await config.get_setting("system_prompt") or DEFAULT_PERSONA
    messages = _inject(messages, persona)

    # 0. Web search / clock grounding / math eval.
    #    Time queries: emit atelier_clock card — no text injection, no web call.
    #    Other queries: classify first, only call Tavily when it would actually help.
    web_trace = None
    clock_data = None
    math_result = None

    if user_text:
        math_result = math_eval.evaluate(user_text)
        if math_result:
            messages = _inject(messages, f"[LOCAL COMPUTE] The exact mathematical/unit result is: {math_result}. Incorporate this seamlessly into a natural response. Do not repeat the equation redundantly.")
        
        weather_match = _WEATHER_Q.search(user_text)
        if weather_match:
            loc = weather_match.group(4).strip()
            if loc:
                w_data = await weather.get_weather(loc)
                if w_data and not w_data.get("error"):
                    messages = _inject(messages, f"[WEATHER DATA] Current weather for {w_data['location']}:\n{w_data}\nAnswer directly using this data.")

        stock_match = _STOCK_Q.search(user_text)
        if stock_match:
            ticker = stock_match.group(3).strip()
            if ticker:
                s_data = await stock.get_stock(ticker)
                if s_data and not s_data.get("error"):
                    messages = _inject(messages, f"[STOCK DATA] Current real-time stock quote for {s_data['symbol']}:\n{s_data}\nAnswer directly using this data.")

    if user_text:
        clock_data = _clock_data(user_text)

    if body.get("web_search") and user_text and not clock_data:
        if _needs_web(user_text):
            try:
                resp = await search.search(user_text, max_results=WEB_RESULTS,
                                           top_k=WEB_TOP_K, want_content=True)
                if resp.results:
                    as_of_str = ""
                    if resp.as_of:
                        as_of_str = f" (fetched {datetime.fromtimestamp(resp.as_of, timezone.utc):%Y-%m-%d})"
                    lines = [
                        f"[WEB SEARCH{as_of_str}] You have live web results below. "
                        "Answer directly from them. Do NOT say you lack web access, "
                        "have a knowledge cutoff, or cannot browse — you are looking at "
                        "real search results right now. Cite the source URLs inline."
                    ]
                    for r in resp.results:
                        body_text = (r.content or r.snippet or "")[:600]
                        lines.append(f"- {r.title} ({r.url})\n  {body_text}")
                    messages = _inject(messages, "\n".join(lines))
                    web_trace = {
                        "query": user_text,
                        "providers": resp.providers_used,
                        "from_cache": resp.from_cache,
                        "as_of": resp.as_of,
                        "results": [
                            {"title": r.title, "url": r.url,
                             "published_at": r.published_at, "stale": r.stale}
                            for r in resp.results
                        ],
                    }
            except Exception:
                pass  # search must never break a reply
        # if neither branch fires, the toggle is on but this message doesn't
        # benefit from search — reply from model knowledge, no trace emitted.

    # 1. Memory + document injection (retrieve is a fast local read).
    atoms = await retrieval.retrieve(user_text, budget_tokens=MEMORY_BUDGET_TOKENS) if user_text else []
    mem_block = retrieval.format_block(atoms)
    doc_filenames = retrieval.doc_sources(atoms)  # for source-chip SSE event
    if mem_block:
        messages = _inject(messages, mem_block)

    # 2. Skill injection (unchanged mechanism).
    enabled = await skills.enabled_skills()
    enabled = [s for s in enabled if s.get("prompt") or s.get("description")]
    if enabled:
        skills_ctx = "You have these skills and capabilities available:\n" + "\n".join(
            f"- {s['name']}: {s.get('prompt') or s.get('description', '')}" for s in enabled
        )
        messages = _inject(messages, skills_ctx)

    payload = {"model": model, "messages": messages, "stream": True}
    for k in ("temperature", "max_tokens"):
        if k in body:
            payload[k] = body[k]

    session_id = body.get("session_id")  # optional; enables source linkage
    if session_id and user_text:
        await sessions.add_message(session_id, "user", user_text, model)

    async def generate():
        assistant_chunks: list[str] = []
        if clock_data:
            yield f"data: {json.dumps({'atelier_clock': clock_data})}\n\n"
            yield "data: [DONE]\n\n"
            return  # card is the complete answer; no LLM call needed
        if doc_filenames:
            yield f"data: {json.dumps({'atelier_docs': doc_filenames})}\n\n"
        if web_trace:
            yield f"data: {json.dumps({'atelier_search': web_trace})}\n\n"
        try:
            async with http_client.client().stream(
                "POST", f"{ep['url']}/chat/completions", json=payload,
                headers=config.headers(ep), timeout=180,
            ) as resp:
                if resp.status_code != 200:
                    err = await resp.aread()
                    yield f"data: {json.dumps({'error': err.decode()})}\n\n"
                    return
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    yield f"{line}\n\n"
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str and data_str != "[DONE]":
                            try:
                                delta = json.loads(data_str)["choices"][0]["delta"].get("content")
                                if delta:
                                    assistant_chunks.append(delta)
                            except Exception:
                                pass
        except Exception as e:  # noqa: BLE001
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

        # 3. Persist assistant turn + enqueue background extraction.
        assistant_text = "".join(assistant_chunks).strip()
        if session_id and assistant_text:
            await sessions.add_message(session_id, "assistant", assistant_text, model)
        if user_text or assistant_text:
            await jobs.enqueue("extract_memory", {
                "user_text": user_text, "assistant_text": assistant_text,
                "source_kind": "chat", "source_id": session_id,
            })

    return StreamingResponse(
        generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
