"""Enricher: decode raw Redis-Stream fields -> ClickHouse `clicks` row tuple.

Expected input (redirect-service XADD payload, see INTEGRATION_CONTRACT.md #5):
    code      : bytes  short_code
    ts        : bytes  unix millis (int as ascii)
    ip        : bytes  client IP (v4 or v6, string form)
    ua        : bytes  User-Agent header
    ref       : bytes  Referer header (may be empty)
    country   : bytes  ISO-3166-1 alpha-2 (redirector already did GeoIP)

Output row matches CH `clicks` table columns (see COLS in writer.py).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import blake2b
from urllib.parse import urlparse

from .bot_detector import is_bot
from .geoip import GeoIPReader
from .logging import get_logger
from .ua import parse_ua

log = get_logger(__name__)


# --- Referer classification ---
_SOCIAL_DOMAINS = frozenset(
    {
        "facebook.com",
        "m.facebook.com",
        "l.facebook.com",
        "instagram.com",
        "t.co",
        "twitter.com",
        "x.com",
        "linkedin.com",
        "lnkd.in",
        "reddit.com",
        "old.reddit.com",
        "pinterest.com",
        "tiktok.com",
        "youtube.com",
        "youtu.be",
        "vk.com",
        "ok.ru",
        "telegram.org",
        "t.me",
        "whatsapp.com",
        "discord.com",
        "snapchat.com",
        "tumblr.com",
    }
)
_SEARCH_DOMAINS = frozenset(
    {
        "google.com",
        "www.google.com",
        "google.co.uk",
        "google.ru",
        "bing.com",
        "www.bing.com",
        "duckduckgo.com",
        "yandex.ru",
        "yandex.com",
        "baidu.com",
        "yahoo.com",
        "search.yahoo.com",
        "ecosia.org",
        "startpage.com",
        "brave.com",
        "search.brave.com",
    }
)
_EMAIL_DOMAINS = frozenset(
    {
        "mail.google.com",
        "mail.yahoo.com",
        "outlook.live.com",
        "outlook.office.com",
        "mail.ru",
        "mail.yandex.ru",
    }
)


def _classify_referer(domain: str) -> str:
    if not domain:
        return "direct"
    d = domain.lower()
    if d in _SOCIAL_DOMAINS:
        return "social"
    if d in _SEARCH_DOMAINS:
        return "search"
    if d in _EMAIL_DOMAINS:
        return "email"
    # suffix fallback (e.g. google.fr, google.de)
    if d.startswith("google.") or d.startswith("bing.") or d.startswith("yandex."):
        return "search"
    return "other"


def _parse_referer(ref: str) -> tuple[str, str]:
    if not ref:
        return "", "direct"
    try:
        p = urlparse(ref if "://" in ref else f"http://{ref}")
        host = (p.hostname or "").lower()
    except Exception:  # noqa: BLE001
        return "", "other"
    return host, _classify_referer(host)


def _hash_ip(ip: str) -> str:
    if not ip:
        return ""
    return blake2b(ip.encode("utf-8", "replace"), digest_size=16).hexdigest()


def _decode(v: bytes | str | None) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return v.decode("utf-8", "replace")


def _get(fields: dict, key: str) -> bytes | None:
    # Redis hiredis returns bytes keys by default; tolerate str keys too.
    bk = key.encode() if isinstance(key, str) else key
    if bk in fields:
        return fields[bk]
    if key in fields:
        return fields[key]
    return None


@dataclass(slots=True, frozen=True)
class EnrichedRow:
    """Ordered attributes matching writer.COLS (CH analytics.clicks schema)."""

    clicked_at: datetime
    short_code: str
    ip_hash: str
    country_code: str
    country_name: str
    region: str
    city: str
    latitude: float
    longitude: float
    device_type: str
    browser: str
    browser_version: str
    os: str
    os_version: str
    is_bot: int
    bot_name: str
    referer_url: str
    referer_domain: str
    referer_type: str
    utm_source: str
    utm_medium: str
    utm_campaign: str

    def as_tuple(self) -> tuple:
        return (
            self.clicked_at,
            self.short_code,
            self.ip_hash,
            self.country_code,
            self.country_name,
            self.region,
            self.city,
            self.latitude,
            self.longitude,
            self.device_type,
            self.browser,
            self.browser_version,
            self.os,
            self.os_version,
            self.is_bot,
            self.bot_name,
            self.referer_url,
            self.referer_domain,
            self.referer_type,
            self.utm_source,
            self.utm_medium,
            self.utm_campaign,
        )


class Enricher:
    """Stateless enricher (holds references to shared GeoIPReader)."""

    __slots__ = ("_geo",)

    def __init__(self, geo: GeoIPReader) -> None:
        self._geo = geo

    def enrich(self, fields: dict) -> EnrichedRow:
        code = _decode(_get(fields, "code"))
        ts_raw = _decode(_get(fields, "ts"))
        ip = _decode(_get(fields, "ip"))
        ua_str = _decode(_get(fields, "ua"))
        ref = _decode(_get(fields, "ref"))
        country_from_stream = _decode(_get(fields, "country"))

        # Event time: prefer ts from stream (ms); fall back to now().
        if ts_raw:
            try:
                ts_ms = int(ts_raw)
                event_time = datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC)
            except (ValueError, OverflowError):
                event_time = datetime.now(UTC)
        else:
            event_time = datetime.now(UTC)

        # GeoIP: if redirector already set country, use it; always attempt full lookup for city/region.
        geo = self._geo.lookup(ip)
        country_code = country_from_stream or (geo.country_code or "")
        country_name = geo.country_name or ""
        region = geo.region or ""
        city = geo.city or ""
        lat = float(geo.lat) if geo.lat is not None else 0.0
        lon = float(geo.lon) if geo.lon is not None else 0.0

        # UA
        ua = parse_ua(ua_str)
        bot = 1 if is_bot(ua_str, ua.browser) else 0

        # Referer
        ref_domain, ref_type = _parse_referer(ref)

        return EnrichedRow(
            clicked_at=event_time,
            short_code=code,
            ip_hash=_hash_ip(ip),
            country_code=country_code,
            country_name=country_name,
            region=region,
            city=city,
            latitude=lat,
            longitude=lon,
            device_type=ua.device_type,
            browser=ua.browser,
            browser_version=ua.browser_version,
            os=ua.os,
            os_version=ua.os_version,
            is_bot=bot,
            bot_name="",
            referer_url=ref,
            referer_domain=ref_domain,
            referer_type=ref_type,
            utm_source="",
            utm_medium="",
            utm_campaign="",
        )
