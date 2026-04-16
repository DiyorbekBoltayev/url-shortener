"""URL safety classifier.

Three backends, selected by ``settings.safety_provider``:

* ``none``           — always returns ``ok``. For dev/CI.
* ``google_web_risk`` — queries the Google Web Risk v1 ``uris:search``
  endpoint. Fails open when the API errors (we never block legitimate
  traffic because an upstream is flaky).
* ``heuristic`` (default) — local denylist + a small set of obvious red
  flags (IPs in host, ``user@host`` cred-in-URL, deeply nested
  subdomains). Cheap, no external calls.

Verdicts are cached in Redis for 24 h keyed by ``sha256(url)`` so the same
URL isn't re-scanned on every create/update.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
from dataclasses import asdict, dataclass
from typing import Literal
from urllib.parse import urlparse

from redis.asyncio import Redis

from app.config import settings
from app.logging import get_logger
from app.services.webhook_service import get_http_client

log = get_logger(__name__)

SafetyStatus = Literal["ok", "warn", "block", "unchecked"]

_CACHE_TTL_SECONDS = 24 * 3600
_WEB_RISK_ENDPOINT = "https://webrisk.googleapis.com/v1/uris:search"
_WEB_RISK_THREAT_TYPES = (
    "MALWARE",
    "SOCIAL_ENGINEERING",
    "UNWANTED_SOFTWARE",
)


@dataclass(slots=True)
class SafetyVerdict:
    status: SafetyStatus
    reason: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "SafetyVerdict":
        data = json.loads(raw)
        return cls(status=data["status"], reason=data.get("reason", ""))


# ----- Public API ---------------------------------------------------------


def _cache_key(url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return f"safety:{digest}"


async def scan(long_url: str, *, cache: Redis | None = None) -> SafetyVerdict:
    """Classify ``long_url``. Read-through cache in Redis for 24h."""
    if cache is not None:
        try:
            cached = await cache.get(_cache_key(long_url))
        except Exception as exc:  # noqa: BLE001
            log.warning("safety_cache_read_failed", err=str(exc))
            cached = None
        if cached:
            try:
                return SafetyVerdict.from_json(cached)
            except Exception:  # noqa: BLE001 — corrupt entry; fall through
                pass

    verdict = await _classify(long_url)

    if cache is not None:
        try:
            await cache.setex(
                _cache_key(long_url), _CACHE_TTL_SECONDS, verdict.to_json()
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("safety_cache_write_failed", err=str(exc))
    return verdict


async def _classify(long_url: str) -> SafetyVerdict:
    provider = settings.safety_provider
    if provider == "none":
        return SafetyVerdict(status="ok")
    if provider == "google_web_risk":
        return await _classify_web_risk(long_url)
    # heuristic (default)
    return _classify_heuristic(long_url)


# ----- Providers ----------------------------------------------------------


async def _classify_web_risk(long_url: str) -> SafetyVerdict:
    api_key = settings.google_web_risk_api_key
    if api_key is None or not api_key.get_secret_value():
        # Missing key — degrade to the heuristic backend so operators
        # still get signal rather than a silent pass.
        return _classify_heuristic(long_url)
    params: list[tuple[str, str]] = [
        ("uri", long_url),
        ("key", api_key.get_secret_value()),
    ]
    for t in _WEB_RISK_THREAT_TYPES:
        params.append(("threatTypes", t))
    try:
        client = get_http_client()
        # Google's public endpoint — not user supplied, safe from SSRF.
        resp = await client.get(_WEB_RISK_ENDPOINT, params=params, timeout=3.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("safety_web_risk_error", err=str(exc))
        # Fail-open: a flaky Google doesn't block creates.
        return SafetyVerdict(status="ok", reason="web_risk_unreachable")
    threat = data.get("threat")
    if not threat:
        return SafetyVerdict(status="ok")
    types = threat.get("threatTypes") or []
    return SafetyVerdict(
        status="block",
        reason=f"google_web_risk: {','.join(types) or 'threat'}",
    )


def _classify_heuristic(long_url: str) -> SafetyVerdict:
    """No-network classifier."""
    try:
        parsed = urlparse(long_url)
    except ValueError:
        return SafetyVerdict(status="warn", reason="unparseable_url")
    host = (parsed.hostname or "").lower()
    if not host:
        return SafetyVerdict(status="warn", reason="missing_host")

    # ----- Denylist — exact host or any suffix match ----------------
    for entry in settings.safety_denylist_domains:
        e = entry.lower().lstrip(".")
        if not e:
            continue
        if host == e or host.endswith("." + e):
            return SafetyVerdict(
                status="warn", reason=f"denylist:{e}"
            )

    # ----- IP literal in host ---------------------------------------
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return SafetyVerdict(
            status="warn", reason="host_is_ip_literal"
        )

    # ----- user@host in URL (phishing staple) ------------------------
    # ``urlparse`` strips userinfo into ``.username`` so check the raw
    # netloc as a belt-and-braces check.
    if parsed.username or "@" in (parsed.netloc or ""):
        return SafetyVerdict(
            status="warn", reason="userinfo_in_url"
        )

    # ----- Excessive subdomain count --------------------------------
    # ``>= 6`` labels (e.g. a.b.c.d.e.tld) is a common obfuscation
    # pattern — cheap, high-signal.
    if host.count(".") >= 5:
        return SafetyVerdict(
            status="warn", reason="excessive_subdomains"
        )

    return SafetyVerdict(status="ok")
