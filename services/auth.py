"""Shared-secret auth with signed sessions (Part 1.6).

The mechanism is built and ready, but enforcement is OPT-IN. On localhost with
no secret configured it stays off, so the single-user local experience needs
zero setup ("keep 127.0.0.1 until auth exists"). Set ATELIER_AUTH=1 (and a
secret via ATELIER_SECRET or the app_config 'shared_secret') before binding to
the LAN / exposing through a tunnel.

When enabled, every /api route is gated except the login route and the public
share download route. Sessions are signed, timed tokens (itsdangerous).
"""
from __future__ import annotations

import hmac
import os

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SESSION_MAX_AGE = 30 * 86400  # 30 days
COOKIE_NAME = "atelier_session"

_serializer: URLSafeTimedSerializer | None = None


def _secret() -> str:
    return os.getenv("ATELIER_SECRET", "atelier-dev-secret")


def _ser() -> URLSafeTimedSerializer:
    global _serializer
    if _serializer is None:
        _serializer = URLSafeTimedSerializer(_secret(), salt="atelier-session")
    return _serializer


def enabled() -> bool:
    return os.getenv("ATELIER_AUTH", "").lower() in ("1", "true", "yes")


def check_secret(provided: str, configured: str | None) -> bool:
    expected = configured or os.getenv("ATELIER_SECRET", "")
    if not expected:
        return False
    return hmac.compare_digest(provided or "", expected)


def issue_session() -> str:
    return _ser().dumps({"ok": True})


def valid_session(token: str | None) -> bool:
    if not token:
        return False
    try:
        _ser().loads(token, max_age=SESSION_MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False
