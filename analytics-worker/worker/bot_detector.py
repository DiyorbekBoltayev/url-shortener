"""Cheap, fast bot detection.

Signals:
  - UA substring match against a compiled regex union of known bot tokens.
  - ua-parser `browser_family` in a known-bots set (handled upstream via ua.py).
  - Missing / implausibly short UA.
  - Known headless-browser markers.

Heavy fingerprinting (TLS JA3, behaviour) lives at the Go redirect edge.
"""
from __future__ import annotations

import re

_BOT_REGEX = re.compile(
    r"bot|crawler|spider|slurp|bingpreview|facebookexternalhit|embedly|quora link preview|"
    r"outbrain|pinterest|vkShare|W3C_Validator|Googlebot|GoogleOther|AdsBot|Mediapartners|"
    r"headlesschrome|phantomjs|selenium|puppeteer|playwright|chrome-lighthouse|"
    r"python-requests|httpx|aiohttp|urllib|curl|wget|go-http-client|okhttp|axios|"
    r"java/|apache-httpclient|libwww|scrapy|masscan|nmap|nikto|zgrab|semrushbot|"
    r"ahrefsbot|mj12bot|dotbot|petalbot|yandexbot|duckduckbot|baiduspider|sogou|"
    r"applebot|linkedinbot|whatsapp|telegrambot|twitterbot|discordbot|slackbot",
    re.IGNORECASE,
)

_KNOWN_BOT_FAMILIES: frozenset[str] = frozenset(
    {
        "Googlebot",
        "Googlebot-Image",
        "Googlebot-News",
        "Googlebot-Video",
        "bingbot",
        "Bingbot",
        "Slurp",
        "DuckDuckBot",
        "Baiduspider",
        "YandexBot",
        "Sogou Spider",
        "Exabot",
        "facebookexternalhit",
        "WhatsApp",
        "Telegrambot",
        "Twitterbot",
        "LinkedInBot",
        "Discordbot",
        "Slackbot",
        "PingdomBot",
        "UptimeRobot",
        "HeadlessChrome",
        "PhantomJS",
        "curl",
        "Wget",
        "python-requests",
        "Python-urllib",
        "Go-http-client",
        "Apache-HttpClient",
        "okhttp",
        "AhrefsBot",
        "SemrushBot",
        "MJ12bot",
    }
)


def is_bot(ua_str: str, ua_family: str = "") -> bool:
    """Return True if the UA looks bot-like."""
    if not ua_str:
        return True
    if len(ua_str) < 8:
        return True
    if ua_family and ua_family in _KNOWN_BOT_FAMILIES:
        return True
    if _BOT_REGEX.search(ua_str):
        return True
    # Generic "Other" with no version signals is suspicious.
    if ua_family == "Other" and "Mozilla" not in ua_str:
        return True
    return False
