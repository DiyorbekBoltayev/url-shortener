"""Base62 encoder/decoder — 0-9, A-Z, a-z."""
from __future__ import annotations

_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_BASE = len(_ALPHABET)
_INDEX = {c: i for i, c in enumerate(_ALPHABET)}


def encode(n: int) -> str:
    """Encode a non-negative integer into a base62 string."""
    if n < 0:
        raise ValueError("n must be non-negative")
    if n == 0:
        return "0"
    out: list[str] = []
    while n:
        n, rem = divmod(n, _BASE)
        out.append(_ALPHABET[rem])
    return "".join(reversed(out))


def decode(s: str) -> int:
    """Decode a base62 string back to an integer."""
    n = 0
    for c in s:
        try:
            n = n * _BASE + _INDEX[c]
        except KeyError as exc:
            raise ValueError(f"invalid base62 character: {c!r}") from exc
    return n
