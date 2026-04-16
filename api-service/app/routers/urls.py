"""URLs CRUD router."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Security, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import (
    primary_workspace_id,
    get_app_redis,
    get_cache_redis,
    get_current_user,
    get_db,
)
from app.models.user import User
from app.schemas.common import Meta, Pagination, SuccessResponse
from app.schemas.url import BulkURLCreate, URLCreate, URLOut, URLUpdate
from app.services import url_service
from app.services.safe_browsing import is_safe

router = APIRouter()
# Public (no auth) shorten router — mounted at /api/v1 in main.py
public_router = APIRouter()

WriteScope = Security(get_current_user, scopes=["urls:write"])
ReadScope = Security(get_current_user, scopes=["urls:read"])


async def _merge_click_counts(cache, rows: list) -> list[URLOut]:
    """Merge Redis click counters into URLOut responses.

    redirect-service does ``INCR clicks:{code}`` on every redirect
    (fire-and-forget). This reads those counters in a single pipeline call
    and adds to the Postgres baseline (``urls.click_count``, kept up-to-
    date by the background sweep — see :mod:`app.main`).
    """
    if not rows:
        return []
    codes = [r.short_code for r in rows]
    pipe = cache.pipeline()
    for c in codes:
        pipe.get(f"clicks:{c}")
        pipe.get(f"clicks:last:{c}")
    results = await pipe.execute()
    out: list[URLOut] = []
    for i, row in enumerate(rows):
        base_total = int(row.click_count or 0)
        live = results[2 * i]
        live_ts = results[2 * i + 1]
        try:
            live_count = int(live) if live is not None else 0
        except (ValueError, TypeError):
            live_count = 0
        dto = URLOut.model_validate(row)
        dto.click_count = base_total + live_count
        if live_ts is not None:
            try:
                dto.last_clicked_at = datetime.fromtimestamp(
                    int(live_ts) / 1000, tz=timezone.utc
                )
            except (ValueError, TypeError):
                pass
        out.append(dto)
    return out


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse[URLOut],
)
async def create_url(
    body: URLCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    cache=Depends(get_cache_redis),
    app_redis=Depends(get_app_redis),
    user: Annotated[User, WriteScope] = ...,
):
    await is_safe(body.long_url)
    workspace_id = await primary_workspace_id(db, user)
    row = await url_service.create_url(
        db,
        cache,
        user_id=user.id,
        workspace_id=workspace_id,
        body=body,
        app_redis=app_redis,
    )
    return {"success": True, "data": URLOut.model_validate(row)}


# NOTE: /alias-check must be declared BEFORE `/{url_id}` so FastAPI doesn't
# treat the literal path segment as a UUID. Auth required to prevent
# slug enumeration by anonymous users.
@router.get("/alias-check", response_model=SuccessResponse[dict])
async def alias_check(
    db: Annotated[AsyncSession, Depends(get_db)],
    alias: str = Query(
        ..., min_length=3, max_length=10, pattern=r"^[A-Za-z0-9_-]+$"
    ),
    user: Annotated[User, ReadScope] = ...,
):
    taken = await url_service.slug_exists(db, slug=alias)
    return {"success": True, "data": {"available": not taken}}


@router.get("", response_model=SuccessResponse[list[URLOut]])
async def list_urls(
    db: Annotated[AsyncSession, Depends(get_db)],
    app_redis=Depends(get_app_redis),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    q: str | None = Query(None, max_length=200),
    folder_id: UUID | None = Query(None),
    tag: str | None = Query(None, max_length=64),
    user: Annotated[User, ReadScope] = ...,
):
    pag = Pagination(page=page, per_page=per_page)
    workspace_id = await primary_workspace_id(db, user)
    rows, total = await url_service.list_urls(
        db,
        user_id=None if workspace_id else user.id,
        workspace_id=workspace_id,
        offset=pag.offset,
        limit=pag.limit,
        search=q,
        folder_id=folder_id,
        tag=tag,
    )
    return {
        "success": True,
        "data": await _merge_click_counts(app_redis, list(rows)),
        "meta": Meta(
            page=pag.page, per_page=pag.per_page, total=total
        ).model_dump(),
    }


@router.get("/{url_id}", response_model=SuccessResponse[URLOut])
async def get_url(
    url_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    app_redis=Depends(get_app_redis),
    user: Annotated[User, ReadScope] = ...,
):
    workspace_id = await primary_workspace_id(db, user)
    row = await url_service.get_url(
        db,
        url_id=url_id,
        user_id=None if workspace_id else user.id,
        workspace_id=workspace_id,
    )
    dtos = await _merge_click_counts(app_redis, [row])
    return {"success": True, "data": dtos[0]}


@router.patch("/{url_id}", response_model=SuccessResponse[URLOut])
async def update_url(
    url_id: UUID,
    body: URLUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    cache=Depends(get_cache_redis),
    app_redis=Depends(get_app_redis),
    user: Annotated[User, WriteScope] = ...,
):
    row = await url_service.update_url(
        db, cache, url_id=url_id, user_id=user.id, body=body, app_redis=app_redis
    )
    return {"success": True, "data": URLOut.model_validate(row)}


@router.delete("/{url_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_url(
    url_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    cache=Depends(get_cache_redis),
    user: Annotated[User, WriteScope] = ...,
):
    workspace_id = await primary_workspace_id(db, user)
    await url_service.delete_url(
        db,
        cache,
        url_id=url_id,
        user_id=None if workspace_id else user.id,
        workspace_id=workspace_id,
    )
    return None


@router.post("/bulk", response_model=SuccessResponse[dict])
async def bulk_create(
    body: BulkURLCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    cache=Depends(get_cache_redis),
    app_redis=Depends(get_app_redis),
    user: Annotated[User, WriteScope] = ...,
):
    """Bulk-create. Each item uses its own SAVEPOINT so a single
    collision / bad URL does not roll back previously-created rows."""
    workspace_id = await primary_workspace_id(db, user)
    created: list[URLOut] = []
    errors: list[dict] = []
    for idx, item in enumerate(body.urls):
        try:
            row = await url_service.create_url(
                db,
                cache,
                user_id=user.id,
                workspace_id=workspace_id,
                body=item,
                app_redis=app_redis,
            )
            created.append(URLOut.model_validate(row))
        except Exception as exc:  # noqa: BLE001
            errors.append({"index": idx, "error": str(exc)})
    return {
        "success": True,
        "data": {
            "created": [c.model_dump(mode="json") for c in created],
            "errors": errors,
            "total_created": len(created),
            "total_errors": len(errors),
        },
    }


# ---- Public (anonymous) shortener --------------------------------------


class ShortenIn(BaseModel):
    long_url: str = Field(min_length=1, max_length=10_000)


@public_router.post("/shorten", response_model=SuccessResponse[dict])
async def public_shorten(
    body: ShortenIn,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    cache=Depends(get_cache_redis),
    app_redis=Depends(get_app_redis),
):
    """Anonymous short-link creation (landing page). Rate-limited by the
    middleware. Returns ``{short_code, short_url}``."""
    await is_safe(body.long_url)
    row = await url_service.create_url(
        db,
        cache,
        user_id=None,
        workspace_id=None,
        body=URLCreate(long_url=body.long_url),
        app_redis=app_redis,
    )
    host = request.headers.get(
        "x-forwarded-host", request.url.netloc
    )
    scheme = request.headers.get(
        "x-forwarded-proto", request.url.scheme
    )
    return {
        "success": True,
        "data": {
            "short_code": row.short_code,
            "short_url": f"{scheme}://{host}/{row.short_code}",
        },
    }
