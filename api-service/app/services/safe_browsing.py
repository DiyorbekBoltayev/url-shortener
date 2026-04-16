"""Back-compat shim — delegates to :mod:`app.services.safety_service`.

Historically this module wrapped Google Safe Browsing v4. The new P0
safety pipeline supersedes it: see
:func:`app.services.safety_service.scan` for the full verdict (ok / warn
/ block with reason) and
:func:`app.services.safety_service._cache_key` for the Redis cache key
format.

The ``is_safe`` helper is kept so existing callers in the redirect path
don't have to change shape — it returns a simple boolean.
"""
from __future__ import annotations

from app.logging import get_logger
from app.services.safety_service import scan

log = get_logger(__name__)


async def is_safe(url: str) -> bool:
    """Return ``True`` when the URL is not classified as a block."""
    try:
        verdict = await scan(url)
    except Exception as exc:  # noqa: BLE001 — never block on internal error
        log.warning("safety_is_safe_error", err=str(exc))
        return True
    # Warn-level URLs still resolve — we surface the warning via
    # ``urls.safety_status`` but don't refuse service.
    return verdict.status != "block"
