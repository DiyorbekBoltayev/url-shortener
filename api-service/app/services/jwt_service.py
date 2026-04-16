"""JWT encode/decode (PyJWT).

Payload keys (HLA section 7):
    sub, workspace_id, plan, scopes, exp, iat, type, jti
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import jwt
from jwt import InvalidTokenError

from app.config import settings

ACCESS = "access"
REFRESH = "refresh"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _encode(payload: dict[str, Any]) -> str:
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_alg,
    )


def issue_access(
    *,
    sub: str,
    workspace_id: str | None,
    plan: str,
    scopes: list[str],
) -> tuple[str, str]:
    jti = str(uuid4())
    now = _now()
    payload = {
        "sub": sub,
        "workspace_id": workspace_id,
        "plan": plan,
        "scopes": scopes,
        "type": ACCESS,
        "iat": now,
        "exp": now + timedelta(seconds=settings.access_ttl_seconds),
        "jti": jti,
    }
    return _encode(payload), jti


def issue_refresh(*, sub: str) -> tuple[str, str]:
    jti = str(uuid4())
    now = _now()
    payload = {
        "sub": sub,
        "type": REFRESH,
        "iat": now,
        "exp": now + timedelta(seconds=settings.refresh_ttl_seconds),
        "jti": jti,
    }
    return _encode(payload), jti


def decode(token: str) -> dict[str, Any]:
    """Decode and verify a token; raises :class:`jwt.InvalidTokenError` on failure."""
    return jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=[settings.jwt_alg],
        options={"require": ["exp", "iat", "sub", "jti", "type"]},
    )


__all__ = ["ACCESS", "REFRESH", "decode", "issue_access", "issue_refresh", "InvalidTokenError"]
