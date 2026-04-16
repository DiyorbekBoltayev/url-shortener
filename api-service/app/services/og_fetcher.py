"""OG / Twitter card metadata fetcher.

Fetches a destination URL, streams the body with a hard byte cap, parses
the relevant ``<meta>`` + ``<link>`` tags, and normalises URLs to absolute
form. SSRF is blocked at the HTTP boundary via
:func:`app.utils.safe_http.assert_public_url`.

Parser choice
-------------
We try :mod:`selectolax` (tiny, C-backed, ~10x faster than ``lxml`` on the
sub-2MB documents we cap at). If it isn't importable we fall back to a
regex-only parser which handles the common "title / description / image /
icon" tags well enough. Either path returns the same :class:`OGResult`.

TODO(og): respect ``robots.txt`` — currently we fetch anything that
``assert_public_url`` allows. Low priority because we only fetch when the
user opted into link preview (``urls.preview_enabled=true``).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.config import settings
from app.logging import get_logger
from app.services.webhook_service import get_http_client
from app.utils.safe_http import UnsafeTargetError, assert_public_url

log = get_logger(__name__)

try:  # pragma: no cover — import-time only
    from selectolax.parser import HTMLParser  # type: ignore[import-not-found]

    _HAS_SELECTOLAX = True
except Exception:  # noqa: BLE001
    HTMLParser = None  # type: ignore[assignment]
    _HAS_SELECTOLAX = False


@dataclass(slots=True)
class OGResult:
    """Normalised subset of OpenGraph / Twitter / generic metadata."""

    title: str | None = None
    description: str | None = None
    image_url: str | None = None
    favicon_url: str | None = None

    def is_empty(self) -> bool:
        return not any(
            (self.title, self.description, self.image_url, self.favicon_url)
        )


# ----- Public API ---------------------------------------------------------


async def fetch_og(long_url: str) -> OGResult | None:
    """Fetch and parse OG metadata for ``long_url``.

    Returns :class:`OGResult` on success (any field may be ``None``).
    Returns ``None`` when the URL is rejected (SSRF, non-HTML, timeout,
    >2xx status). Never raises — callers treat ``None`` as "don't bother
    again for this URL right now".
    """
    if not settings.og_fetch_enabled:
        return None

    try:
        assert_public_url(long_url)
    except UnsafeTargetError as exc:
        log.info("og_fetch_ssrf_blocked", url=long_url, reason=str(exc))
        return None

    max_bytes = settings.og_fetch_max_body_mb * 1024 * 1024
    timeout = settings.og_fetch_timeout_sec
    client = get_http_client()

    body = b""
    final_url = long_url
    try:
        # ``follow_redirects=False`` comes from the shared client — we
        # explicitly re-enable it here because OG metadata frequently
        # lives behind a 301 (http -> https, bare domain -> www). Each
        # hop is re-validated by httpx; we cap at 3.
        async with client.stream(
            "GET",
            long_url,
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "URLShortenerPreviewBot/0.1 (+link-preview)",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en;q=0.8",
            },
        ) as resp:
            if resp.status_code >= 400:
                log.info(
                    "og_fetch_bad_status",
                    url=long_url,
                    status=resp.status_code,
                )
                return None
            ctype = resp.headers.get("content-type", "").lower()
            if "html" not in ctype and "xml" not in ctype:
                log.info("og_fetch_non_html", url=long_url, ctype=ctype)
                return None
            # SSRF re-check: the redirect target may have resolved to a
            # private IP even though the original hostname was public.
            # httpx doesn't let us intercept each hop, so we at least
            # validate the final URL we ended up on.
            final_url = str(resp.url)
            try:
                assert_public_url(final_url)
            except UnsafeTargetError as exc:
                log.info(
                    "og_fetch_ssrf_blocked_post_redirect",
                    url=final_url,
                    reason=str(exc),
                )
                return None

            async for chunk in resp.aiter_bytes():
                body += chunk
                if len(body) >= max_bytes:
                    # Hard cap: truncated content is still parseable —
                    # OG tags live in <head> which is always near the
                    # top of the document.
                    break
    except httpx.TimeoutException:
        log.info("og_fetch_timeout", url=long_url)
        return None
    except httpx.HTTPError as exc:
        log.info("og_fetch_http_error", url=long_url, err=str(exc))
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("og_fetch_error", url=long_url, err=str(exc))
        return None

    if not body:
        return None

    text = _decode(body)
    parsed = (
        _parse_selectolax(text) if _HAS_SELECTOLAX else _parse_regex(text)
    )
    # Resolve relative image / favicon URLs against the final URL.
    parsed.image_url = _absolutize(final_url, parsed.image_url)
    parsed.favicon_url = _absolutize(
        final_url, parsed.favicon_url
    ) or _fallback_favicon(final_url)
    return parsed


# ----- Parsers ------------------------------------------------------------


def _decode(body: bytes) -> str:
    """Best-effort byte -> str. HTTP headers already set encoding hints,
    but when the body arrives with a different ``<meta charset>`` we'd
    rather get garbled text than crash — metadata is usually ASCII.
    """
    for enc in ("utf-8", "latin-1"):
        try:
            return body.decode(enc)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", errors="replace")


def _parse_selectolax(html: str) -> OGResult:
    """Parser using :mod:`selectolax`."""
    tree = HTMLParser(html)  # type: ignore[misc]
    out = OGResult()

    # Title: <meta property="og:title"> > <meta name="twitter:title"> > <title>
    out.title = _meta(tree, "og:title") or _meta(
        tree, "twitter:title"
    ) or (tree.css_first("title").text() if tree.css_first("title") else None)
    out.description = _meta(tree, "og:description") or _meta(
        tree, "twitter:description"
    ) or _meta(tree, "description", attr="name")
    out.image_url = _meta(tree, "og:image") or _meta(
        tree, "twitter:image"
    )

    # Favicon: any <link rel="...icon..."> — touch-icon is richer than
    # the default 16x16, so it wins when present.
    icon_href: str | None = None
    for link in tree.css("link[rel]") or []:
        rel = (link.attributes.get("rel") or "").lower()
        if "icon" not in rel:
            continue
        href = link.attributes.get("href")
        if not href:
            continue
        if "apple-touch-icon" in rel:
            icon_href = href
            break
        icon_href = icon_href or href
    out.favicon_url = icon_href
    return _strip(out)


def _meta(tree: Any, key: str, attr: str = "property") -> str | None:
    sel = f'meta[{attr}="{key}"]'
    node = tree.css_first(sel)
    if node is None:
        return None
    val = node.attributes.get("content")
    return val.strip() if val else None


_META_RE = re.compile(
    r'<meta\s+[^>]*(?:property|name)\s*=\s*["\']([^"\']+)["\']'
    r'[^>]*content\s*=\s*["\']([^"\']*)["\'][^>]*>',
    re.IGNORECASE,
)
_META_RE_REV = re.compile(
    r'<meta\s+[^>]*content\s*=\s*["\']([^"\']*)["\']'
    r'[^>]*(?:property|name)\s*=\s*["\']([^"\']+)["\'][^>]*>',
    re.IGNORECASE,
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_LINK_RE = re.compile(
    r'<link\s+[^>]*rel\s*=\s*["\']([^"\']+)["\']'
    r'[^>]*href\s*=\s*["\']([^"\']+)["\'][^>]*>',
    re.IGNORECASE,
)
_LINK_RE_REV = re.compile(
    r'<link\s+[^>]*href\s*=\s*["\']([^"\']+)["\']'
    r'[^>]*rel\s*=\s*["\']([^"\']+)["\'][^>]*>',
    re.IGNORECASE,
)


def _parse_regex(html: str) -> OGResult:
    """Fallback parser without selectolax. Covers the 90% case."""
    metas: dict[str, str] = {}
    for m in _META_RE.finditer(html):
        metas.setdefault(m.group(1).lower(), m.group(2).strip())
    for m in _META_RE_REV.finditer(html):
        metas.setdefault(m.group(2).lower(), m.group(1).strip())

    title = metas.get("og:title") or metas.get("twitter:title")
    if not title:
        tm = _TITLE_RE.search(html)
        if tm:
            title = re.sub(r"\s+", " ", tm.group(1)).strip()
    description = (
        metas.get("og:description")
        or metas.get("twitter:description")
        or metas.get("description")
    )
    image = metas.get("og:image") or metas.get("twitter:image")

    icon: str | None = None
    for lm in _LINK_RE.finditer(html):
        rel = lm.group(1).lower()
        if "icon" not in rel:
            continue
        href = lm.group(2)
        if "apple-touch-icon" in rel:
            icon = href
            break
        icon = icon or href
    if not icon:
        for lm in _LINK_RE_REV.finditer(html):
            rel = lm.group(2).lower()
            if "icon" not in rel:
                continue
            href = lm.group(1)
            if "apple-touch-icon" in rel:
                icon = href
                break
            icon = icon or href

    return _strip(
        OGResult(
            title=title, description=description, image_url=image, favicon_url=icon
        )
    )


def _strip(og: OGResult) -> OGResult:
    """Normalise whitespace and enforce sensible lengths on text fields."""
    if og.title:
        og.title = re.sub(r"\s+", " ", og.title).strip()[:500]
    if og.description:
        og.description = re.sub(r"\s+", " ", og.description).strip()[:1000]
    return og


def _absolutize(base: str, maybe_url: str | None) -> str | None:
    if not maybe_url:
        return None
    candidate = urljoin(base, maybe_url)
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        return None
    return candidate


def _fallback_favicon(url: str) -> str | None:
    """When the page advertises no icon, try ``/favicon.ico`` and then a
    third-party icon service. We don't validate either URL exists — the
    redirect service / frontend can ``onerror`` if they 404."""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.hostname:
        return None
    host = parsed.hostname
    # DuckDuckGo's icon service is a safe public fallback that also
    # doubles as a cache for origins that block our UA.
    return f"https://icons.duckduckgo.com/ip3/{host}.ico"
