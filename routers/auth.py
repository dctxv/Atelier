"""Auth: status + login (Part 1.6). No-op friendly when auth is disabled."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from services import auth, config

router = APIRouter(prefix="/api/auth")


@router.get("/status")
async def status():
    return {"enabled": auth.enabled()}


@router.post("/login")
async def login(request: Request):
    data = await request.json()
    if not auth.enabled():
        return {"ok": True, "enabled": False}
    configured = await config.get_setting("shared_secret")
    if not auth.check_secret(data.get("secret", ""), configured):
        return JSONResponse({"ok": False, "error": "invalid secret"}, status_code=401)
    resp = JSONResponse({"ok": True})
    resp.set_cookie(
        auth.COOKIE_NAME, auth.issue_session(),
        httponly=True, samesite="lax", max_age=auth.SESSION_MAX_AGE,
    )
    return resp
