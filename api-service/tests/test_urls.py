"""URL CRUD happy path."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_create_url_requires_auth(client):
    r = await client.post("/api/v1/urls", json={"long_url": "https://example.com"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_base62_encode():
    from app.utils import base62

    assert base62.encode(0) == "0"
    assert base62.encode(61) == "z"
    assert base62.decode("10") == 62
    assert base62.decode(base62.encode(123456789)) == 123456789


@pytest.mark.asyncio
async def test_url_validator():
    from app.utils.url_validator import InvalidUrlError, validate_long_url

    assert validate_long_url("https://example.com/a") == "https://example.com/a"
    with pytest.raises(InvalidUrlError):
        validate_long_url("javascript:alert(1)")
    with pytest.raises(InvalidUrlError):
        validate_long_url("https://x\r\ny")
    with pytest.raises(InvalidUrlError):
        validate_long_url("https://")  # no netloc
