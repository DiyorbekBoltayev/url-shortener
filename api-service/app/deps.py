"""FastAPI dependencies — auth, DB, workspace resolution."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

import redis.asyncio as aioredis
from clickhouse_connect.driver.asyncclient import AsyncClient as CHClient
from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer, SecurityScopes
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clickhouse_client, redis_client
from app.database import get_session
from app.models.api_key import ApiKey
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services import jwt_service
from app.utils.hashing import hash_key

oauth2 = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    scopes={
        "urls:read": "Read URLs",
        "urls:write": "Create/update URLs",
        "analytics:read": "Read analytics",
        "admin": "Administrative",
    },
    auto_error=False,
)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


# ---- Basic providers ------------------------------------------------

async def get_db(session: Annotated[AsyncSession, Depends(get_session)]) -> AsyncSession:
    return session


def get_cache_redis() -> aioredis.Redis:
    return redis_client.get_cache_redis()


def get_app_redis() -> aioredis.Redis:
    return redis_client.get_app_redis()


def get_ch() -> CHClient:
    return clickhouse_client.get_clickhouse()


# ---- Current user (JWT) --------------------------------------------

async def _decode_access(token: str, redis: aioredis.Redis) -> dict:
    try:
        payload = jwt_service.decode(token)
    except InvalidTokenError as exc:
        raise HTTPException(401, "Invalid token") from exc
    if payload.get("type") != jwt_service.ACCESS:
        raise HTTPException(401, "Wrong token type")
    jti = payload.get("jti")
    if jti and await redis.get(f"revoked:{jti}"):
        raise HTTPException(401, "Token revoked")
    return payload


async def get_current_user(
    security_scopes: SecurityScopes,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[str | None, Depends(oauth2)] = None,
    raw_api_key: Annotated[str | None, Depends(api_key_header)] = None,
) -> User:
    """Authenticate via Bearer JWT or X-API-Key header."""
    www = f'Bearer scope="{security_scopes.scope_str}"' if security_scopes.scopes else "Bearer"
    headers = {"WWW-Authenticate": www}

    # --- JWT path ---
    if token:
        payload = await _decode_access(token, get_app_redis())
        try:
            uid = UUID(payload["sub"])
        except (KeyError, ValueError) as exc:
            raise HTTPException(401, "Bad subject", headers=headers) from exc
        user = await db.scalar(select(User).where(User.id == uid, User.is_active.is_(True)))
        if not user:
            raise HTTPException(401, "User not found", headers=headers)
        token_scopes = payload.get("scopes") or []
        for need in security_scopes.scopes:
            if need not in token_scopes and "admin" not in token_scopes:
                raise HTTPException(403, "Missing scope", headers=headers)
        request.state.auth = {"type": "jwt", "payload": payload, "user_id": str(user.id)}
        return user

    # --- API-key path ---
    if raw_api_key:
        digest = hash_key(raw_api_key)
        row = await db.scalar(
            select(ApiKey).where(ApiKey.key_hash == digest, ApiKey.is_active.is_(True))
        )
        if not row:
            raise HTTPException(403, "Invalid API key", headers=headers)
        user = await db.scalar(select(User).where(User.id == row.user_id, User.is_active.is_(True)))
        if not user:
            raise HTTPException(403, "API key owner inactive", headers=headers)
        scopes = set(row.scopes or [])
        needed = set(security_scopes.scopes)
        if needed and not needed.issubset({f"urls:{s}" if s in {"read", "write"} else s
                                           for s in scopes} | scopes):
            raise HTTPException(403, "Missing scope", headers=headers)
        request.state.auth = {
            "type": "api_key",
            "api_key_id": str(row.id),
            "user_id": str(user.id),
        }
        return user

    raise HTTPException(401, "Not authenticated", headers=headers)


async def get_current_workspace(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Workspace:
    ws = await db.scalar(select(Workspace).where(Workspace.owner_id == user.id).limit(1))
    if not ws:
        raise HTTPException(403, "No workspace bound to user")
    return ws


async def primary_workspace_id(
    db: AsyncSession, user: User
) -> UUID | None:
    """Resolve the user's primary workspace id.

    Order:
      1. owner role in workspace_members (preferred)
      2. any workspace where user is owner_id
      3. None (unscoped — allowed for legacy callers)
    """
    row = await db.scalar(
        select(WorkspaceMember.workspace_id).where(
            WorkspaceMember.user_id == user.id,
            WorkspaceMember.role == "owner",
        ).limit(1)
    )
    if row:
        return row
    ws = await db.scalar(
        select(Workspace.id).where(Workspace.owner_id == user.id).limit(1)
    )
    return ws
