"""Users router — profile + quick listings."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.common import Meta, Pagination
from app.schemas.url import URLOut
from app.schemas.user import UserOut, UserUpdate
from app.services import url_service

router = APIRouter()
ReadScope = Security(get_current_user, scopes=["urls:read"])


@router.get("/me")
async def me(user: Annotated[User, ReadScope]):
    return {"success": True, "data": UserOut.model_validate(user)}


@router.patch("/me")
async def update_me(
    body: UserUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, ReadScope] = ...,
):
    """Update current user.

    Accepts ``full_name`` and ``email``. Other fields are silently ignored.
    Email changes require uniqueness — a conflict is surfaced via the
    IntegrityError handler as 409.
    """
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.email is not None and body.email.lower() != (user.email or "").lower():
        user.email = body.email.lower()
        # Uniqueness enforced by the UNIQUE index on users.email; the
        # IntegrityError handler converts a collision to a 409 envelope.
    await db.flush()
    await db.refresh(user)
    return {"success": True, "data": UserOut.model_validate(user)}


@router.get("/me/urls")
async def my_urls(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    user: Annotated[User, ReadScope] = ...,
):
    pag = Pagination(page=page, per_page=per_page)
    rows, total = await url_service.list_urls(
        db, user_id=user.id, workspace_id=None,
        offset=pag.offset, limit=pag.limit,
    )
    return {
        "success": True,
        "data": [URLOut.model_validate(r) for r in rows],
        "meta": Meta(page=pag.page, per_page=pag.per_page, total=total).model_dump(),
    }
