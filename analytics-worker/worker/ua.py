"""ua-parser wrapper with LRU-cached parse (keyed by blake2b hash of UA).

Raw UA strings are untrusted input; caching them as `lru_cache` keys directly
would let adversarial traffic (random UAs) blow up memory. Hashing keeps each
key fixed at 16 bytes.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from hashlib import blake2b

from ua_parser import user_agent_parser


@dataclass(slots=True, frozen=True)
class UA:
    browser: str
    browser_version: str
    os: str
    os_version: str
    device_family: str
    device_type: str  # "mobile" | "tablet" | "desktop" | "other"


_EMPTY = UA("", "", "", "", "", "other")


def _hash(ua: str) -> bytes:
    return blake2b(ua.encode("utf-8", "replace"), digest_size=16).digest()


_MOBILE_HINTS = ("Mobile", "iPhone", "Android", "Phone")
_TABLET_HINTS = ("Tablet", "iPad", "Kindle")


def _classify_device(device_family: str, os_family: str) -> str:
    fam = (device_family or "").strip()
    osf = (os_family or "").strip()
    hay = f"{fam} {osf}"
    if any(h in hay for h in _TABLET_HINTS):
        return "tablet"
    if any(h in hay for h in _MOBILE_HINTS):
        return "mobile"
    if fam in {"", "Other"} and osf in {"", "Other"}:
        return "other"
    return "desktop"


@lru_cache(maxsize=10_000)
def _parse_cached(_h: bytes, ua_str: str) -> UA:
    p = user_agent_parser.Parse(ua_str)
    browser = p["user_agent"]["family"] or ""
    browser_ver = p["user_agent"]["major"] or ""
    os_fam = p["os"]["family"] or ""
    os_ver = p["os"]["major"] or ""
    dev_fam = p["device"]["family"] or ""
    device_type = _classify_device(dev_fam, os_fam)
    return UA(
        browser=browser,
        browser_version=browser_ver,
        os=os_fam,
        os_version=os_ver,
        device_family=dev_fam,
        device_type=device_type,
    )


def parse_ua(ua_str: str) -> UA:
    """Parse a UA string, returning a cached immutable `UA` record."""
    if not ua_str:
        return _EMPTY
    return _parse_cached(_hash(ua_str), ua_str)


def cache_info() -> str:
    return str(_parse_cached.cache_info())


def clear_cache() -> None:
    _parse_cached.cache_clear()
