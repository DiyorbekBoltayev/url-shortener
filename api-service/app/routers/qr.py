"""QR code router — ``/api/v1/urls/{id}/qr`` + style persistence."""
from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Security
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_cache_redis, get_current_user, get_db
from app.models.user import User
from app.schemas.common import SuccessResponse
from app.schemas.qr import QRStyle
from app.services import qr_service, url_service

router = APIRouter()
ReadScope = Security(get_current_user, scopes=["urls:read"])
WriteScope = Security(get_current_user, scopes=["urls:write"])


def _merge_style(stored: dict | None, override: QRStyle | None) -> QRStyle | None:
    """Layer per-request overrides on top of the persisted style.

    Overrides are only applied for preview — they never touch the DB row.
    """
    base: dict = dict(stored) if stored else {}
    if override is not None:
        base.update(override.model_dump(exclude_none=True))
    if not base:
        return None
    return QRStyle.model_validate(base)


@router.get("/{url_id}/qr")
async def qr(
    url_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_cache_redis),
    fmt: Literal["png", "svg"] = Query("png"),
    size: int = Query(512, ge=64, le=2048),
    # ---- Inline style overrides (preview only) ----------------------------
    fg: str | None = Query(default=None, max_length=7),
    bg: str | None = Query(default=None, max_length=7),
    logo_url: str | None = Query(default=None, max_length=500),
    frame: Literal["none", "rounded", "square"] | None = Query(default=None),
    dots: Literal["square", "rounded", "extra-rounded"] | None = Query(default=None),
    corners: Literal["square", "rounded", "extra-rounded"] | None = Query(default=None),
    eye_color: str | None = Query(default=None, max_length=7),
    user: Annotated[User, ReadScope] = ...,
):
    row = await url_service.get_url(db, url_id=url_id, user_id=user.id)

    override: QRStyle | None = None
    if any(v is not None for v in (fg, bg, logo_url, frame, dots, corners, eye_color)):
        # model_validate runs the same regex/enum checks as the persisted
        # path — so junk values get rejected with 422 before rendering.
        override = QRStyle.model_validate(
            {
                "fg": fg,
                "bg": bg,
                "logo_url": logo_url,
                "frame": frame,
                "dots": dots,
                "corners": corners,
                "eye_color": eye_color,
            }
        )

    style = _merge_style(row.qr_style, override)
    content = f"/{row.short_code}"

    if fmt == "svg":
        data = await qr_service.generate_svg(
            content, size=size, style=style, url_id=row.id, redis=redis
        )
        return Response(content=data, media_type="image/svg+xml")

    data = await qr_service.generate_png(
        content, size=size, style=style, url_id=row.id, redis=redis
    )
    return Response(content=data, media_type="image/png")


@router.post(
    "/{url_id}/qr-style",
    response_model=SuccessResponse[QRStyle],
)
async def save_qr_style(
    url_id: UUID,
    body: QRStyle,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, WriteScope] = ...,
):
    """Persist a QR style as the default for this URL."""
    row = await url_service.get_url(db, url_id=url_id, user_id=user.id)
    row.qr_style = body.model_dump(exclude_none=True)
    await db.flush()
    await db.refresh(row)
    return {"success": True, "data": QRStyle.model_validate(row.qr_style or {})}
