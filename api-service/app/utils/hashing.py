"""Hashing + API-key generation helpers (sha256)."""
from __future__ import annotations

import hashlib
import secrets


API_KEY_PREFIX = "usk_"
_TOKEN_BYTES = 32


def generate_api_key() -> tuple[str, str, str]:
    """Return ``(raw, hash, visible_prefix)`` for a fresh API key.

    Callers store the hash only; the raw string is shown to the user once.
    """
    raw = API_KEY_PREFIX + secrets.token_urlsafe(_TOKEN_BYTES)
    digest = hash_key(raw)
    visible_prefix = raw[:10]  # e.g. "usk_a3BxK9"
    return raw, digest, visible_prefix


def hash_key(raw: str) -> str:
    """Return the hex sha256 of a raw API key (used for DB lookup)."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
