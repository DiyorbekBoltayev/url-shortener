"""Bot detector unit tests."""
from __future__ import annotations

import pytest

from worker.bot_detector import is_bot


@pytest.mark.parametrize(
    "ua, family, expected",
    [
        ("", "", True),  # empty UA
        ("short", "", True),  # too short
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Chrome",
            False,
        ),
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            "Mobile Safari",
            False,
        ),
        (
            "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
            "Googlebot",
            True,
        ),
        ("curl/7.88.1", "curl", True),
        ("python-requests/2.31.0", "Python Requests", True),
        ("facebookexternalhit/1.1", "facebookexternalhit", True),
        (
            "Mozilla/5.0 (X11; Linux x86_64) HeadlessChrome/120.0.6099.109 Safari/537.36",
            "HeadlessChrome",
            True,
        ),
        ("Go-http-client/1.1", "Go-http-client", True),
    ],
)
def test_is_bot(ua: str, family: str, expected: bool):
    assert is_bot(ua, family) is expected
