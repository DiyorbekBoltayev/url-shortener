"""OG fetcher — happy path with mocked httpx stream."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import og_fetcher


class _AsyncStream:
    """Minimal ``async with`` + ``aiter_bytes`` stand-in for httpx response."""

    def __init__(self, body: bytes, status: int = 200, ctype: str = "text/html"):
        self._body = body
        self.status_code = status
        self.headers = {"content-type": ctype}
        self.url = "https://example.com/"

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def aiter_bytes(self):
        yield self._body


@pytest.mark.asyncio
async def test_fetch_og_parses_meta_tags():
    html = (
        b"<html><head>"
        b'<title>Fallback</title>'
        b'<meta property="og:title" content="Hello OG">'
        b'<meta property="og:description" content="desc">'
        b'<meta property="og:image" content="/img.png">'
        b'<link rel="icon" href="/favicon.ico">'
        b"</head><body></body></html>"
    )
    fake = _AsyncStream(html)
    fake_client = MagicMock()
    fake_client.stream = MagicMock(return_value=fake)

    # Bypass SSRF: assert_public_url raises on localhost/test domains.
    with patch(
        "app.services.og_fetcher.assert_public_url", return_value=None
    ), patch(
        "app.services.og_fetcher.get_http_client", return_value=fake_client
    ):
        result = await og_fetcher.fetch_og("https://example.com/")

    assert result is not None
    assert result.title == "Hello OG"
    assert result.description == "desc"
    assert result.image_url == "https://example.com/img.png"
    # Favicon absolutised against the final URL.
    assert result.favicon_url == "https://example.com/favicon.ico"


@pytest.mark.asyncio
async def test_fetch_og_falls_back_to_duckduckgo_favicon():
    html = (
        b"<html><head>"
        b'<meta property="og:title" content="T">'
        b"</head></html>"
    )
    fake = _AsyncStream(html)
    fake_client = MagicMock()
    fake_client.stream = MagicMock(return_value=fake)

    with patch(
        "app.services.og_fetcher.assert_public_url", return_value=None
    ), patch(
        "app.services.og_fetcher.get_http_client", return_value=fake_client
    ):
        result = await og_fetcher.fetch_og("https://example.com/x")

    assert result is not None
    assert result.favicon_url is not None
    assert "duckduckgo.com" in result.favicon_url


@pytest.mark.asyncio
async def test_fetch_og_rejects_non_html():
    fake = _AsyncStream(b"\x00\x01\x02", ctype="application/pdf")
    fake_client = MagicMock()
    fake_client.stream = MagicMock(return_value=fake)

    with patch(
        "app.services.og_fetcher.assert_public_url", return_value=None
    ), patch(
        "app.services.og_fetcher.get_http_client", return_value=fake_client
    ):
        result = await og_fetcher.fetch_og("https://example.com/x.pdf")

    assert result is None


@pytest.mark.asyncio
async def test_fetch_og_ssrf_returns_none():
    from app.utils.safe_http import UnsafeTargetError

    with patch(
        "app.services.og_fetcher.assert_public_url",
        side_effect=UnsafeTargetError("private"),
    ):
        result = await og_fetcher.fetch_og("http://127.0.0.1/")
    assert result is None
