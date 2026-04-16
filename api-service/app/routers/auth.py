"""Auth router — register, login, refresh, logout."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Security, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_app_redis, get_current_user, get_db
from app.models.user import User
from app.schemas.auth import (
    LoginIn,
    LoginOut,
    LogoutIn,
    PasswordChangeIn,
    RefreshIn,
    RegisterIn,
    TokenOut,
    UserPublic,
)
from app.schemas.common import SuccessResponse
from app.services import auth_service, jwt_service

router = APIRouter()


def _user_public(user) -> UserPublic:
    return UserPublic(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        plan=user.plan,
        is_active=user.is_active,
        is_verified=user.is_verified,
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse[LoginOut],
)
async def register(
    body: RegisterIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_app_redis),
):
    user, _ws = await auth_service.register_user(
        db, email=body.email, password=body.password, full_name=body.full_name
    )
    access, refresh, expires_in = await auth_service.issue_token_pair(
        db, redis=redis, user=user
    )
    return {
        "success": True,
        "data": LoginOut(
            tokens=TokenOut(
                access_token=access, refresh_token=refresh, expires_in=expires_in
            ),
            user=_user_public(user),
        ),
    }


@router.post("/login", response_model=SuccessResponse[LoginOut])
async def login(
    body: LoginIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_app_redis),
):
    user = await auth_service.authenticate(db, email=body.email, password=body.password)
    access, refresh, expires_in = await auth_service.issue_token_pair(
        db, redis=redis, user=user
    )
    return {
        "success": True,
        "data": LoginOut(
            tokens=TokenOut(
                access_token=access, refresh_token=refresh, expires_in=expires_in
            ),
            user=_user_public(user),
        ),
    }


@router.post("/refresh", response_model=SuccessResponse[TokenOut])
async def refresh(
    body: RefreshIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_app_redis),
):
    access, new_refresh, expires_in = await auth_service.refresh_tokens(
        db, redis=redis, refresh_token=body.refresh_token
    )
    return {
        "success": True,
        "data": TokenOut(
            access_token=access, refresh_token=new_refresh, expires_in=expires_in
        ),
    }


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    request: Request,
    body: LogoutIn,
    redis=Depends(get_app_redis),
):
    # Best-effort: if a bearer is present, revoke it.
    access_payload: dict = {}
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        try:
            access_payload = jwt_service.decode(auth_header.split(" ", 1)[1])
        except Exception:
            access_payload = {}
    await auth_service.logout(
        redis,
        access_payload=access_payload,
        refresh_token=body.refresh_token,
    )
    return {"success": True, "data": {"logged_out": True}}


@router.post("/password", response_model=SuccessResponse[dict])
async def change_password(
    body: PasswordChangeIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[
        User, Security(get_current_user, scopes=["urls:write"])
    ] = ...,
):
    """Change the authenticated user's password.

    Body: ``{current_password, new_password}``.
    """
    await auth_service.change_password(
        db, user=user, current=body.current_password, new=body.new_password
    )
    return {"success": True, "data": {"changed": True}}
