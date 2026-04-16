"""URL CRUD service — owns transactions & Redis cache writes."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.exceptions import BadRequest, Conflict, NotFound
from app.logging import get_logger
from app.models.retarget_pixel import RetargetPixel
from app.models.url import Url
from app.schemas.url import URLCreate, URLUpdate
from app.services import kgs_service, safety_service
from app.services.auth_service import hash_password
from app.utils.url_validator import InvalidUrlError, validate_long_url

log = get_logger(__name__)

URL_CACHE_TTL_SECONDS = 86_400

# Redis list keys consumed by the background workers in ``app.main``.
OG_FETCH_QUEUE = "og:fetch:queue"
SAFETY_SCAN_QUEUE = "safety:scan:queue"
# Budget for the synchronous safety check on create/update; anything
# slower is deferred to the async worker.
_SYNC_SAFETY_BUDGET_SEC = 0.5


async def enqueue_og_fetch(app_redis: Redis, url_id: UUID) -> None:
    """LPUSH a URL id onto the OG fetch queue. Silent on failure."""
    try:
        await app_redis.lpush(OG_FETCH_QUEUE, str(url_id))
    except Exception as exc:  # noqa: BLE001
        log.warning("og_enqueue_failed", url_id=str(url_id), err=str(exc))


async def enqueue_safety_scan(app_redis: Redis, url_id: UUID) -> None:
    try:
        await app_redis.lpush(SAFETY_SCAN_QUEUE, str(url_id))
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "safety_enqueue_failed", url_id=str(url_id), err=str(exc)
        )


async def _sync_safety_or_queue(
    row: Url,
    *,
    cache_redis: Redis,
    app_redis: Redis | None,
) -> None:
    """Best-effort synchronous safety scan on create/update.

    We give the scanner up to :data:`_SYNC_SAFETY_BUDGET_SEC` so the API
    can return ``ok``/``warn``/``block`` in the response. If the scanner
    isn't done in time we leave ``safety_status='unchecked'`` and defer
    to the async worker via :data:`SAFETY_SCAN_QUEUE`.
    """
    try:
        verdict = await asyncio.wait_for(
            safety_service.scan(row.long_url, cache=cache_redis),
            timeout=_SYNC_SAFETY_BUDGET_SEC,
        )
    except asyncio.TimeoutError:
        if app_redis is not None:
            await enqueue_safety_scan(app_redis, row.id)
        return
    except Exception as exc:  # noqa: BLE001
        log.warning("safety_sync_scan_failed", err=str(exc))
        if app_redis is not None:
            await enqueue_safety_scan(app_redis, row.id)
        return
    row.safety_status = verdict.status
    row.safety_reason = verdict.reason or None
    row.safety_checked_at = datetime.now(timezone.utc)


def _cache_key(short_code: str) -> str:
    return f"url:{short_code}"


def _cache_meta_key(short_code: str) -> str:
    return f"url:meta:{short_code}"


def _cache_rules_key(short_code: str) -> str:
    return f"url:rules:{short_code}"


def _cache_pixels_key(short_code: str) -> str:
    return f"url:pixels:{short_code}"


def _pixel_to_cache_dict(pixel: RetargetPixel) -> dict[str, object]:
    return {
        "kind": pixel.kind,
        "pixel_id": pixel.pixel_id,
        "is_active": bool(pixel.is_active),
    }


async def _write_cache(redis: Redis, url_row: Url) -> None:
    """Write the Redis cache entries the redirect-service reads.

    Covers the base ``url:{code}`` value plus the enriched
    ``url:meta:{code}`` hash (see FEATURES_PLAN §"Redis cache row
    enrichment") and the optional ``url:rules:{code}`` /
    ``url:pixels:{code}`` side-tables.
    """
    key = _cache_key(url_row.short_code)
    meta_key = _cache_meta_key(url_row.short_code)
    await redis.setex(key, URL_CACHE_TTL_SECONDS, url_row.long_url)

    has_rules = bool(url_row.routing_rules)
    # Only read `pixels` if already loaded — accessing a lazy relationship
    # in async context raises MissingGreenlet. On initial create pixels
    # are always empty; on update the caller must eagerly-load (selectinload)
    # before passing the row here.
    from sqlalchemy import inspect as sa_inspect
    insp = sa_inspect(url_row)
    if "pixels" in insp.unloaded:
        pixels: list = []
    else:
        pixels = list(getattr(url_row, "pixels", []) or [])
    has_pixels = bool(pixels)

    meta: dict[str, str] = {
        "is_active": "1" if url_row.is_active else "0",
        "has_password": "1" if url_row.password_hash else "0",
        "has_rules": "1" if has_rules else "0",
        "has_pixels": "1" if has_pixels else "0",
        "safety_status": url_row.safety_status or "unchecked",
    }
    if url_row.expires_at:
        meta["expires_at"] = url_row.expires_at.isoformat()
    if url_row.max_clicks is not None:
        meta["max_clicks"] = str(url_row.max_clicks)
    await redis.hset(meta_key, mapping=meta)
    await redis.expire(meta_key, URL_CACHE_TTL_SECONDS)

    rules_key = _cache_rules_key(url_row.short_code)
    if has_rules:
        await redis.setex(
            rules_key,
            URL_CACHE_TTL_SECONDS,
            json.dumps(url_row.routing_rules, separators=(",", ":")),
        )
    else:
        await redis.delete(rules_key)

    pixels_key = _cache_pixels_key(url_row.short_code)
    if has_pixels:
        payload = [_pixel_to_cache_dict(p) for p in pixels]
        await redis.setex(
            pixels_key,
            URL_CACHE_TTL_SECONDS,
            json.dumps(payload, separators=(",", ":")),
        )
    else:
        await redis.delete(pixels_key)


async def _invalidate_cache(redis: Redis, short_code: str) -> None:
    await redis.delete(
        _cache_key(short_code),
        _cache_meta_key(short_code),
        _cache_rules_key(short_code),
        _cache_pixels_key(short_code),
    )


async def slug_exists(db: AsyncSession, *, slug: str) -> bool:
    """Cheap availability check used by `GET /urls/alias-check`."""
    row = await db.scalar(select(Url.id).where(Url.short_code == slug))
    return row is not None


async def create_url(
    db: AsyncSession,
    cache_redis: Redis,
    *,
    user_id: UUID | None,
    workspace_id: UUID | None,
    body: URLCreate,
    app_redis: Redis | None = None,
) -> Url:
    """Create a URL. ``app_redis`` is used to pop pool codes; falls back
    to ``cache_redis`` when not supplied (kept for backward compat)."""
    try:
        long_url = validate_long_url(body.long_url)
    except InvalidUrlError as exc:
        raise BadRequest(str(exc), code="INVALID_URL") from exc

    short_code = body.custom_slug
    if short_code:
        existing = await db.scalar(
            select(Url.id).where(Url.short_code == short_code)
        )
        if existing:
            raise Conflict(f"Short code '{short_code}' is already taken")

    pool_redis = app_redis or cache_redis

    routing_rules = (
        body.routing_rules.model_dump(exclude_none=True)
        if body.routing_rules is not None
        else None
    )

    # Persist with collision-retry for auto-generated codes -------------
    last_exc: Exception | None = None
    for _ in range(5):
        code = short_code or await kgs_service.next_short_code(pool_redis)
        row = Url(
            short_code=code,
            long_url=long_url,
            title=body.title,
            user_id=user_id,
            workspace_id=workspace_id,
            domain_id=body.domain_id,
            folder_id=body.folder_id,
            expires_at=body.expires_at,
            password_hash=hash_password(body.password) if body.password else None,
            max_clicks=body.max_clicks,
            tags=list(body.tags),
            utm_source=body.utm_source,
            utm_medium=body.utm_medium,
            utm_campaign=body.utm_campaign,
            routing_rules=routing_rules,
            qr_style=(
                body.qr_style.model_dump(exclude_none=True)
                if body.qr_style is not None
                else None
            ),
            preview_enabled=bool(body.preview_enabled)
            if body.preview_enabled is not None
            else False,
        )
        try:
            async with db.begin_nested():  # SAVEPOINT — isolates this attempt
                db.add(row)
                await db.flush()
        except IntegrityError as exc:
            last_exc = exc
            if short_code:
                # Custom slug cannot be retried.
                raise Conflict(
                    f"Short code '{short_code}' is already taken"
                ) from None
            continue
        # Synchronous safety first so the response reflects the verdict
        # — if it times out, defer to the async worker.
        await _sync_safety_or_queue(
            row, cache_redis=cache_redis, app_redis=app_redis
        )
        await _write_cache(cache_redis, row)
        # OG preview is strictly async: the API never blocks on it.
        if app_redis is not None and row.preview_enabled and settings.og_fetch_enabled:
            await enqueue_og_fetch(app_redis, row.id)
        return row

    raise Conflict(
        "Could not generate a unique short code after retries",
        code="KGS_EXHAUSTED",
    ) from last_exc


async def get_url(
    db: AsyncSession, *, url_id: UUID, user_id: UUID | None = None,
    workspace_id: UUID | None = None,
) -> Url:
    stmt = select(Url).where(Url.id == url_id)
    if workspace_id is not None:
        stmt = stmt.where(Url.workspace_id == workspace_id)
    elif user_id is not None:
        stmt = stmt.where(Url.user_id == user_id)
    row = await db.scalar(stmt)
    if not row:
        raise NotFound("URL not found")
    return row


async def list_urls(
    db: AsyncSession,
    *,
    user_id: UUID | None,
    workspace_id: UUID | None,
    offset: int,
    limit: int,
    search: str | None = None,
    folder_id: UUID | None = None,
    tag: str | None = None,
) -> tuple[list[Url], int]:
    base = select(Url)
    if workspace_id is not None:
        base = base.where(Url.workspace_id == workspace_id)
    elif user_id is not None:
        base = base.where(Url.user_id == user_id)
    if search:
        like = f"%{search}%"
        base = base.where((Url.short_code.ilike(like)) | (Url.long_url.ilike(like)))
    if folder_id is not None:
        base = base.where(Url.folder_id == folder_id)
    if tag:
        # Postgres array-contains via SQLAlchemy operator.
        base = base.where(Url.tags.any(tag))

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    rows = (
        await db.execute(
            base.order_by(Url.created_at.desc()).offset(offset).limit(limit)
        )
    ).scalars().all()
    return list(rows), int(total)


async def update_url(
    db: AsyncSession,
    cache_redis: Redis,
    *,
    url_id: UUID,
    user_id: UUID,
    body: URLUpdate,
    app_redis: Redis | None = None,
) -> Url:
    row = await get_url(db, url_id=url_id, user_id=user_id)
    data = body.model_dump(exclude_unset=True)
    # Validate the updated long_url when supplied.
    if "long_url" in data and data["long_url"] is not None:
        try:
            data["long_url"] = validate_long_url(data["long_url"])
        except InvalidUrlError as exc:
            raise BadRequest(str(exc), code="INVALID_URL") from exc
    # Track the pre-update values of fields that influence background jobs.
    prev_long_url = row.long_url
    prev_preview_enabled = bool(row.preview_enabled)

    if "password" in data:
        pwd = data.pop("password")
        row.password_hash = hash_password(pwd) if pwd else None
    if "qr_style" in data:
        qr = data.pop("qr_style")
        if qr is None:
            row.qr_style = None
        elif hasattr(qr, "model_dump"):
            row.qr_style = qr.model_dump(exclude_none=True)
        else:
            row.qr_style = {k: v for k, v in dict(qr).items() if v is not None}
    if "routing_rules" in data:
        rr = data.pop("routing_rules")
        if rr is None:
            row.routing_rules = None
        elif hasattr(rr, "model_dump"):
            row.routing_rules = rr.model_dump(exclude_none=True)
        else:
            row.routing_rules = dict(rr)
    for field, value in data.items():
        setattr(row, field, value)

    long_url_changed = row.long_url != prev_long_url
    preview_turned_on = bool(row.preview_enabled) and not prev_preview_enabled

    if long_url_changed:
        # Re-scan safety synchronously against the new destination; fall
        # through to the async queue on timeout. Existing og_* fields are
        # cleared so the UI doesn't show stale metadata while we refetch.
        row.safety_status = "unchecked"
        row.safety_reason = None
        row.safety_checked_at = None
        await _sync_safety_or_queue(
            row, cache_redis=cache_redis, app_redis=app_redis
        )
        row.og_title = None
        row.og_description = None
        row.og_image_url = None
        row.favicon_url = None
        row.og_fetched_at = None

    await db.flush()
    await db.refresh(row)
    # Re-write the full cache snapshot (routing, pixels, meta) rather than
    # just invalidating — redirect-service keeps the denormalised copy.
    await _write_cache(cache_redis, row)

    if (
        app_redis is not None
        and settings.og_fetch_enabled
        and row.preview_enabled
        and (long_url_changed or preview_turned_on)
    ):
        await enqueue_og_fetch(app_redis, row.id)
    return row


async def delete_url(
    db: AsyncSession, cache_redis: Redis, *, url_id: UUID, user_id: UUID | None = None,
    workspace_id: UUID | None = None,
) -> None:
    row = await get_url(db, url_id=url_id, user_id=user_id, workspace_id=workspace_id)
    code = row.short_code
    await db.delete(row)
    await db.flush()
    await _invalidate_cache(cache_redis, code)


async def get_url_by_code(
    db: AsyncSession, *, short_code: str, user_id: UUID | None = None
) -> Url:
    stmt = select(Url).where(Url.short_code == short_code)
    if user_id is not None:
        stmt = stmt.where(Url.user_id == user_id)
    row = await db.scalar(stmt)
    if not row:
        raise NotFound("URL not found")
    return row


async def rewrite_pixel_cache(
    db: AsyncSession, cache_redis: Redis, *, url_id: UUID
) -> None:
    """Refresh url:meta has_pixels + url:pixels after an attach/detach.

    Services mutating ``link_pixels`` call this so redirect-service sees
    the change before the JSON cache TTL expires.
    """
    row = await db.scalar(select(Url).where(Url.id == url_id))
    if row is None:
        return
    await db.refresh(row, attribute_names=["pixels"])
    await _write_cache(cache_redis, row)
