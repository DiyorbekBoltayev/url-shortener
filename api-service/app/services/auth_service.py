"""Auth service — register, login, refresh, logout.

Uses :mod:`pwdlib` (argon2 default, bcrypt fallback) — not passlib.
"""
from __future__ import annotations

from uuid import UUID

from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.exceptions import Conflict, Unauthorized
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services import jwt_service

# Recommended ≈ argon2 primary + bcrypt verifier (for legacy hashes).
_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _password_hash.verify(password, hashed)
    except Exception:
        return False


def _slugify_email(email: str) -> str:
    """Naive slug from the local-part; DB has UNIQUE(slug) so collisions raise."""
    local = email.split("@", 1)[0].lower()
    out = []
    for c in local:
        if c.isalnum():
            out.append(c)
        elif c in "-_.":
            out.append("-")
    slug = "".join(out).strip("-") or "user"
    return slug[:80]


async def register_user(
    db: AsyncSession, *, email: str, password: str, full_name: str | None
) -> tuple[User, Workspace]:
    existing = await db.scalar(select(User).where(User.email == email.lower()))
    if existing:
        raise Conflict("Email already registered")

    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        full_name=full_name,
        is_active=True,
        is_verified=False,
        plan="free",
    )
    db.add(user)
    await db.flush()

    # Personal workspace
    base_slug = _slugify_email(email)
    slug = base_slug
    suffix = 0
    while await db.scalar(select(Workspace).where(Workspace.slug == slug)):
        suffix += 1
        slug = f"{base_slug}-{suffix}"

    ws = Workspace(name=f"{user.full_name or email.split('@', 1)[0]}'s workspace",
                   slug=slug, owner_id=user.id, plan="free")
    db.add(ws)
    await db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
    await db.flush()
    return user, ws


async def authenticate(db: AsyncSession, *, email: str, password: str) -> User:
    user = await db.scalar(select(User).where(User.email == email.lower()))
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        raise Unauthorized("Invalid email or password")
    return user


async def get_primary_workspace(db: AsyncSession, user_id: UUID) -> Workspace | None:
    return await db.scalar(
        select(Workspace).where(Workspace.owner_id == user_id).limit(1)
    )


async def issue_token_pair(
    db: AsyncSession, *, redis, user: User
) -> tuple[str, str, int]:
    """Issue access+refresh and register the refresh jti in Redis."""
    ws = await get_primary_workspace(db, user.id)
    workspace_id = str(ws.id) if ws else None
    scopes = ["urls:read", "urls:write", "analytics:read"]
    if user.plan == "enterprise":
        scopes.append("admin")

    access, _ = jwt_service.issue_access(
        sub=str(user.id),
        workspace_id=workspace_id,
        plan=user.plan,
        scopes=scopes,
    )
    refresh, rjti = jwt_service.issue_refresh(sub=str(user.id))

    await redis.setex(
        f"rt:{user.id}:{rjti}",
        settings.refresh_ttl_seconds,
        "1",
    )
    return access, refresh, settings.access_ttl_seconds


async def refresh_tokens(
    db: AsyncSession, *, redis, refresh_token: str
) -> tuple[str, str, int]:
    try:
        payload = jwt_service.decode(refresh_token)
    except Exception as exc:
        raise Unauthorized("Invalid refresh token") from exc
    if payload.get("type") != jwt_service.REFRESH:
        raise Unauthorized("Wrong token type")

    sub = payload["sub"]
    jti = payload["jti"]
    # Single-use: DEL returns 1 if the key existed (consume).
    deleted = await redis.delete(f"rt:{sub}:{jti}")
    if not deleted:
        raise Unauthorized("Refresh token already used or revoked")

    user = await db.get(User, UUID(sub))
    if not user or not user.is_active:
        raise Unauthorized("User no longer active")
    return await issue_token_pair(db, redis=redis, user=user)


async def change_password(
    db: AsyncSession, *, user: User, current: str, new: str
) -> None:
    """Verify `current` then replace the user's password hash."""
    if not verify_password(current, user.password_hash):
        raise Unauthorized("Current password is incorrect")
    if current == new:
        raise Conflict("New password must differ from the current password")
    user.password_hash = hash_password(new)
    await db.flush()


async def logout(redis, *, access_payload: dict, refresh_token: str | None) -> None:
    """Revoke the current access jti and, if provided, the refresh jti."""
    access_jti = access_payload.get("jti")
    if access_jti:
        ttl = max(1, int(access_payload["exp"]) - int(access_payload["iat"]))
        await redis.setex(f"revoked:{access_jti}", ttl, "1")
    if refresh_token:
        try:
            rp = jwt_service.decode(refresh_token)
            await redis.delete(f"rt:{rp['sub']}:{rp['jti']}")
        except Exception:
            pass
