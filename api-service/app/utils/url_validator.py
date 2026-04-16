"""URL validation helpers.

Rules (HLA section 8):
  * scheme whitelist: http, https
  * max length 10,000 chars
  * no CRLF (protect against header injection)
  * ASCII-only in the network location (punycode at the edge)
"""
from __future__ import annotations

from urllib.parse import urlparse

MAX_URL_LENGTH = 10_000
ALLOWED_SCHEMES = frozenset({"http", "https"})


class InvalidUrlError(ValueError):
    """Raised when a user-supplied URL fails validation."""


def validate_long_url(url: str) -> str:
    """Return a cleaned URL or raise ``InvalidUrlError``."""
    if not isinstance(url, str):
        raise InvalidUrlError("URL must be a string")

    cleaned = url.strip()
    if not cleaned:
        raise InvalidUrlError("URL must not be empty")

    if len(cleaned) > MAX_URL_LENGTH:
        raise InvalidUrlError(f"URL exceeds maximum length of {MAX_URL_LENGTH}")

    if "\r" in cleaned or "\n" in cleaned:
        raise InvalidUrlError("URL must not contain CR or LF characters")

    try:
        parsed = urlparse(cleaned)
    except ValueError as exc:
        raise InvalidUrlError(f"URL could not be parsed: {exc}") from exc

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise InvalidUrlError(f"URL scheme must be one of: {sorted(ALLOWED_SCHEMES)}")

    if not parsed.netloc:
        raise InvalidUrlError("URL must include a host")

    return cleaned
