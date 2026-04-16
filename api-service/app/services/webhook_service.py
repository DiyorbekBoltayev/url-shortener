"""Webhook service — CRUD + HMAC-signed fire-and-forget dispatch."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
import time
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

from app.config import settings
from app.exceptions import BadRequest, NotFound
from app.logging import get_logger
from app.models.webhook import Webhook
from app.utils.safe_http import UnsafeTargetError, assert_public_url

log = get_logger(__name__)


# ---- Shared HTTP client ----------------------------------------------
#
# A single pool is reused across all webhook and third-party calls. The
# client is created lazily (so imports stay cheap) and closed on app
# shutdown via :func:`close_http_client`.
_http_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        # follow_redirects=False — SSRF guard on the original URL only.
        _http_client = httpx.AsyncClient(
            timeout=5.0, http2=True, follow_redirects=False
        )
    return _http_client


async def close_http_client() -> None:
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        try:
            await _http_client.aclose()
        finally:
            _http_client = None


# ---- Background task bookkeeping -------------------------------------

_background_tasks: set[asyncio.Task] = set()


def _gen_secret() -> str:
    return "whsec_" + secrets.token_urlsafe(32)


def sign_payload(secret: str, payload: bytes, timestamp: int) -> str:
    """HMAC-SHA256 signature — ``t=<ts>,v1=<hex>``."""
    msg = f"{timestamp}.".encode() + payload
    mac = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={mac}"


async def create_webhook(
    db: AsyncSession, *, workspace_id: UUID, url: str, events: list[str]
) -> Webhook:
    # SSRF guard (RV10 1.4). Reject private/loopback/link-local/reserved
    # targets at ingestion — we re-check just before each dispatch to close
    # the DNS rebinding / TOCTOU window.
    try:
        assert_public_url(url)
    except UnsafeTargetError as exc:
        raise BadRequest(
            f"webhook URL rejected: {exc}",
            code="UNSAFE_WEBHOOK_URL",
        ) from exc

    row = Webhook(
        workspace_id=workspace_id,
        url=url,
        secret=_gen_secret(),
        events=list(events),
        is_active=True,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


async def list_webhooks(
    db: AsyncSession, *, workspace_id: UUID, offset: int, limit: int
) -> tuple[list[Webhook], int]:
    base = select(Webhook).where(Webhook.workspace_id == workspace_id)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        await db.execute(base.order_by(Webhook.created_at.desc()).offset(offset).limit(limit))
    ).scalars().all()
    return list(rows), int(total)


async def _load_webhook(
    db: AsyncSession, *, workspace_id: UUID, webhook_id: UUID
) -> Webhook:
    row = await db.scalar(
        select(Webhook).where(
            Webhook.id == webhook_id, Webhook.workspace_id == workspace_id
        )
    )
    if not row:
        raise NotFound("Webhook not found")
    return row


async def update_webhook(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    webhook_id: UUID,
    url: str | None = None,
    events: list[str] | None = None,
    is_active: bool | None = None,
) -> Webhook:
    row = await _load_webhook(
        db, workspace_id=workspace_id, webhook_id=webhook_id
    )
    if url is not None:
        try:
            assert_public_url(url)
        except UnsafeTargetError as exc:
            raise BadRequest(
                f"webhook URL rejected: {exc}",
                code="UNSAFE_WEBHOOK_URL",
            ) from exc
        row.url = url
    if events is not None:
        row.events = list(events)
    if is_active is not None:
        row.is_active = is_active
    await db.flush()
    await db.refresh(row)
    return row


async def delete_webhook(
    db: AsyncSession, *, workspace_id: UUID, webhook_id: UUID
) -> None:
    row = await _load_webhook(
        db, workspace_id=workspace_id, webhook_id=webhook_id
    )
    await db.delete(row)
    await db.flush()


async def deliver_test(
    db: AsyncSession, *, workspace_id: UUID, webhook_id: UUID
) -> bool:
    """Fire a single test ping to the webhook's URL."""
    row = await _load_webhook(
        db, workspace_id=workspace_id, webhook_id=webhook_id
    )
    try:
        assert_public_url(row.url)
    except UnsafeTargetError as exc:
        log.warning(
            "webhook_test_blocked_ssrf",
            webhook_id=str(row.id),
            reason=str(exc),
        )
        return False
    body = json.dumps(
        {
            "event": "ping",
            "data": {"test": True, "ts": int(time.time())},
            "webhook_id": str(row.id),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    ts = int(time.time())
    sig = sign_payload(
        row.secret or settings.webhook_signing_key.get_secret_value(),
        body,
        ts,
    )
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": sig,
        "X-Webhook-Event": "ping",
    }
    try:
        resp = await get_http_client().post(
            row.url, content=body, headers=headers
        )
        return 200 <= resp.status_code < 300
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "webhook_test_failed", webhook_id=str(row.id), err=str(exc)
        )
        return False


async def dispatch(
    webhook: Webhook, event: str, data: dict[str, Any]
) -> None:
    """Send a signed POST to ``webhook.url``; retries with exp backoff."""
    if not webhook.is_active or event not in (webhook.events or []):
        return
    body = json.dumps(
        {"event": event, "data": data, "webhook_id": str(webhook.id)},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    ts = int(time.time())
    sig = sign_payload(webhook.secret or settings.webhook_signing_key.get_secret_value(),
                       body, ts)
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": sig,
        "X-Webhook-Event": event,
    }
    # Re-check at dispatch time (RV10 1.4): DNS for the stored hostname may
    # have flipped to a private address since create_webhook validated it.
    try:
        assert_public_url(webhook.url)
    except UnsafeTargetError as exc:
        log.warning(
            "webhook_dispatch_blocked_ssrf",
            webhook_id=str(webhook.id),
            reason=str(exc),
        )
        return

    client = get_http_client()
    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.5, max=5),
            reraise=True,
        ):
            with attempt:
                # ``follow_redirects=False`` on the shared client prevents
                # a 30x response from bouncing us to an internal address.
                resp = await client.post(webhook.url, content=body, headers=headers)
                resp.raise_for_status()
    except Exception as exc:
        log.warning("webhook_dispatch_failed", webhook_id=str(webhook.id), err=str(exc))


def dispatch_background(webhook: Webhook, event: str, data: dict[str, Any]) -> None:
    """Fire-and-forget helper — schedules ``dispatch`` on the current loop.

    The task reference is retained so the asyncio loop doesn't GC it mid-
    flight (CPython can otherwise drop untracked tasks).
    """
    task = asyncio.create_task(dispatch(webhook, event, data))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
