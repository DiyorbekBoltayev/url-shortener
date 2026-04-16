"""MinIO / S3-compatible client.

We use the lean :mod:`minio` package (roughly 1/10th the wheel size of
``boto3``) because the bits we need — ``put_object``, presigned GET,
``make_bucket`` — are exactly what ``minio-py`` is good at. Switching to
``boto3`` later would only require swapping this module; nothing outside
talks to the client directly.

The client calls are all synchronous. To keep the event loop unblocked we
drive them through :func:`asyncio.to_thread` in the wrappers below.
"""
from __future__ import annotations

import asyncio
import io
from datetime import timedelta
from typing import Any

from app.config import settings
from app.logging import get_logger

log = get_logger(__name__)

try:  # pragma: no cover — import-time only
    from minio import Minio  # type: ignore[import-not-found]
    from minio.error import S3Error  # type: ignore[import-not-found]

    _HAS_MINIO = True
except Exception:  # noqa: BLE001
    Minio = None  # type: ignore[assignment]
    S3Error = Exception  # type: ignore[assignment,misc]
    _HAS_MINIO = False


_client: Any | None = None


def _endpoint_and_secure() -> tuple[str, bool]:
    """Extract ``host:port`` + secure flag from ``settings.minio_endpoint``.

    Accepts bare ``host:port`` (falls back to ``minio_secure``) or full
    ``http(s)://host:port`` URLs. Callers typically just configure the
    bare form in ``.env`` so this is mostly a safety net.
    """
    ep = settings.minio_endpoint
    secure = settings.minio_secure
    if ep.startswith("https://"):
        ep = ep[len("https://") :]
        secure = True
    elif ep.startswith("http://"):
        ep = ep[len("http://") :]
        secure = False
    # Strip any trailing path / slashes — Minio() wants host:port only.
    ep = ep.rstrip("/").split("/", 1)[0]
    return ep, secure


def get_client() -> Any | None:
    """Return the initialised client, constructing it on first call.

    Returns ``None`` when the ``minio`` dependency isn't installed (dev
    environments that don't need import/export). Callers must guard for
    this so we degrade gracefully instead of hard-crashing.
    """
    global _client
    if _client is not None:
        return _client
    if not _HAS_MINIO:
        log.warning("minio_client_unavailable", reason="minio package missing")
        return None
    endpoint, secure = _endpoint_and_secure()
    _client = Minio(
        endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key.get_secret_value(),
        secure=secure,
    )
    return _client


async def ensure_bucket(name: str) -> bool:
    """Idempotently create ``name`` if missing. Returns ``True`` on ok."""
    client = get_client()
    if client is None:
        return False

    def _ensure() -> bool:
        try:
            if not client.bucket_exists(name):
                client.make_bucket(name)
            return True
        except S3Error as exc:
            # Rare race: two processes calling make_bucket at once will
            # see one win with BucketAlreadyOwnedByYou. Treat as success.
            if getattr(exc, "code", "") in {
                "BucketAlreadyOwnedByYou",
                "BucketAlreadyExists",
            }:
                return True
            raise

    try:
        return await asyncio.to_thread(_ensure)
    except Exception as exc:  # noqa: BLE001
        log.warning("minio_ensure_bucket_failed", bucket=name, err=str(exc))
        return False


async def ensure_default_buckets() -> None:
    """Ensure all known buckets exist. Safe to call repeatedly."""
    for bucket in (
        settings.minio_bucket_exports,
        settings.minio_bucket_imports,
        settings.minio_bucket_qr_logos,
    ):
        await ensure_bucket(bucket)


async def upload_bytes(
    bucket: str,
    key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> bool:
    """Upload an in-memory blob. Returns ``True`` on success."""
    client = get_client()
    if client is None:
        return False

    def _put() -> bool:
        buf = io.BytesIO(data)
        client.put_object(
            bucket,
            key,
            buf,
            length=len(data),
            content_type=content_type,
        )
        return True

    try:
        return await asyncio.to_thread(_put)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "minio_upload_failed", bucket=bucket, key=key, err=str(exc)
        )
        return False


async def presign_get(bucket: str, key: str, expires: int = 86_400) -> str | None:
    """Return a presigned GET URL valid for ``expires`` seconds (default 24h)."""
    client = get_client()
    if client is None:
        return None

    def _presign() -> str:
        return client.presigned_get_object(
            bucket, key, expires=timedelta(seconds=expires)
        )

    try:
        return await asyncio.to_thread(_presign)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "minio_presign_failed", bucket=bucket, key=key, err=str(exc)
        )
        return None
