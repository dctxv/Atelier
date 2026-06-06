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

from services import config, http_client, retrieval, skills
from workers import jobs

router = APIRouter(prefix="/api")

MEMORY_BUDGET_TOKENS = 700


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

    # 1. Memory injection (retrieve is a fast local read).
    atoms = await retrieval.retrieve(user_text, budget_tokens=MEMORY_BUDGET_TOKENS) if user_text else []
    mem_block = retrieval.format_block(atoms)
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

    async def generate():
        assistant_chunks: list[str] = []
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

        # 3. Enqueue background extraction (never blocks the stream).
        assistant_text = "".join(assistant_chunks).strip()
        if user_text or assistant_text:
            await jobs.enqueue("extract_memory", {
                "user_text": user_text, "assistant_text": assistant_text,
                "source_kind": "chat", "source_id": session_id,
            })

    return StreamingResponse(
        generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
