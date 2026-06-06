"""Notes co-writer — selection-based AI actions, streamed (Part 2.4).

continue / rewrite / tighten stream tokens like chat. Context comes from the
shared retrieve() so the co-writer knows what the rest of the workspace knows.
Uses the active model; the budget target is first-token < 300 ms with a local
model (network models will be slower — that's a model property, not app cost).
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from services import config, http_client, retrieval

router = APIRouter(prefix="/api")

_ACTIONS = {
    "continue": "Continue the user's writing naturally from where it stops. Match voice and tone. Output only the continuation.",
    "rewrite": "Rewrite the selected text to be clearer and better written, preserving meaning. Output only the rewritten text.",
    "tighten": "Tighten the selected text: remove redundancy, make it concise, keep the meaning and voice. Output only the tightened text.",
}


@router.post("/notes/cowrite")
async def cowrite(request: Request):
    body = await request.json()
    action = body.get("action", "continue")
    if action not in _ACTIONS:
        raise HTTPException(400, f"Unknown action '{action}'")
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text required")

    ep = await config.active_endpoint_raw()
    if not ep:
        raise HTTPException(400, "No endpoint configured")
    model = await config.get_setting("active_model")
    if not model:
        raise HTTPException(400, "No model selected")

    atoms = await retrieval.retrieve(text, budget_tokens=400)
    mem_block = retrieval.format_block(atoms)
    system = _ACTIONS[action]
    if mem_block:
        system += "\n\n" + mem_block

    payload = {
        "model": model, "stream": True, "temperature": 0.6,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": text}],
    }

    async def generate():
        try:
            async with http_client.client().stream(
                "POST", f"{ep['url']}/chat/completions", json=payload,
                headers=config.headers(ep), timeout=120,
            ) as resp:
                if resp.status_code != 200:
                    err = await resp.aread()
                    yield f"data: {json.dumps({'error': err.decode()})}\n\n"
                    return
                async for line in resp.aiter_lines():
                    if line:
                        yield f"{line}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
