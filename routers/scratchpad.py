"""Scratchpad — per-line local evaluation (the "living margin", §10.3).

POST /api/scratchpad/eval  {text}  ->  {results: [{value, kind, name?}]}

Pure-local: reuses math_eval + local_tools with a simple per-pad symbol table,
so `a = 5` then `b = a * 2` resolves. No model, no network for these lines.
Lines starting with `?` are flagged kind="ask" (the client routes those to chat).
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Request

from services import math_eval, local_tools

router = APIRouter(prefix="/api")

_ASSIGN = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*(.+)$")
_NUMERIC = re.compile(r"^-?\d+(?:\.\d+)?$")


def _eval_line(expr: str) -> str | None:
    expr = (expr or "").strip()
    if not expr:
        return None
    try:
        r = math_eval.evaluate(expr)
        if r:
            return str(r)
    except Exception:
        pass
    try:
        card = local_tools.try_local(expr)
        if card and card.get("result"):
            return str(card["result"])
    except Exception:
        pass
    return None


@router.post("/scratchpad/eval")
async def scratchpad_eval(request: Request):
    data = await request.json()
    text = data.get("text") or ""
    vars_: dict[str, str] = {}
    results: list[dict] = []

    def subst(s: str) -> str:
        for name, val in vars_.items():
            s = re.sub(rf"\b{re.escape(name)}\b", f"({val})", s)
        return s

    for raw in text.split("\n"):
        stripped = raw.strip()
        if not stripped:
            results.append({"value": None, "kind": "blank"})
            continue
        if stripped.startswith("#") or stripped.startswith("//"):
            results.append({"value": None, "kind": "comment"})
            continue
        if stripped.startswith("?"):
            results.append({"value": None, "kind": "ask"})
            continue

        m = _ASSIGN.match(stripped)
        if m:
            name, rhs = m.group(1), m.group(2)
            resolved = subst(rhs).strip()
            val = _eval_line(resolved)
            if val is None and _NUMERIC.match(resolved):
                val = resolved
            if val is not None:
                vars_[name] = val
                results.append({"value": val, "kind": "assign", "name": name})
            else:
                results.append({"value": None, "kind": "none"})
            continue

        results.append({"value": _eval_line(subst(stripped)), "kind": "value"})

    return {"results": results}
