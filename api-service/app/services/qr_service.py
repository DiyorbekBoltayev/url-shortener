"""QR-code rendering (PNG + SVG) — branded styling support (P0-2).

Supports per-URL styling via :class:`app.schemas.qr.QRStyle`:

- foreground/background colors (hex)
- dot + corner module drawers (square / rounded / extra-rounded)
- optional center logo (downloaded via SSRF-guarded httpx, <=512 KB)
- optional frame (rounded / square border)

Results are cached in Redis for 1 hour keyed by
``qr:{url_id}:{style_hash}:{size}:{fmt}``. Rendering is intended to stay
under 200ms p95; the hot path (no logo download, no cache miss) is purely
in-process PIL work.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import re
from typing import Any, Literal
from uuid import UUID
from xml.sax.saxutils import escape as xml_escape

import qrcode
from qrcode.constants import ERROR_CORRECT_H, ERROR_CORRECT_M
from qrcode.image.pil import PilImage
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.colormasks import SolidFillColorMask
from qrcode.image.styles.moduledrawers.pil import (
    CircleModuleDrawer,
    RoundedModuleDrawer,
    SquareModuleDrawer,
)
from qrcode.image.svg import SvgImage, SvgPathImage

from app.exceptions import BadRequest
from app.schemas.qr import QRStyle
from app.utils.safe_http import UnsafeTargetError, assert_public_url

log = logging.getLogger(__name__)

Format = Literal["png", "svg"]

# ---------------------------------------------------------------------------
# Tuning knobs
# ---------------------------------------------------------------------------

_QR_CACHE_TTL_SECONDS = 3600
_LOGO_MAX_BYTES = 512 * 1024  # 512 KB hard ceiling
_LOGO_TIMEOUT = 5.0
_SVG_LOGO_MAX_BYTES = 100 * 1024  # inline data-URI size cap
_FRAME_PADDING = 18
_DEFAULT_FG = "#000000"
_DEFAULT_BG = "#FFFFFF"

_HEX_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


# ---------------------------------------------------------------------------
# Colour + contrast utilities
# ---------------------------------------------------------------------------


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    """Convert ``#rgb`` / ``#rrggbb`` to an ``(r, g, b)`` tuple.

    Relies on :data:`_HEX_RE` having been applied upstream — :class:`QRStyle`
    already validates, but we re-check here to defend against styles coming
    from the DB with unexpected values.
    """
    if not _HEX_RE.match(h):
        raise BadRequest(f"Invalid hex colour: {h!r}", code="QR_INVALID_COLOR")
    s = h.lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    def chan(c: int) -> float:
        cs = c / 255.0
        return cs / 12.92 if cs <= 0.03928 else ((cs + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG relative contrast ratio between two hex colours."""
    la = _relative_luminance(_hex_to_rgb(fg))
    lb = _relative_luminance(_hex_to_rgb(bg))
    light, dark = max(la, lb), min(la, lb)
    return (light + 0.05) / (dark + 0.05)


# ---------------------------------------------------------------------------
# Style hashing (cache key component)
# ---------------------------------------------------------------------------


def _style_dict(style: QRStyle | None) -> dict[str, Any]:
    if style is None:
        return {}
    return style.model_dump(exclude_none=True)


def style_hash(style: QRStyle | None) -> str:
    """Short deterministic hash of the resolved style — cache key fragment."""
    data = _style_dict(style)
    blob = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha1(blob, usedforsecurity=False).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Logo fetch (PNG path only)
# ---------------------------------------------------------------------------


async def _fetch_logo(url: str) -> bytes | None:
    """Download a remote logo. Returns ``None`` on any failure.

    Applies the project's SSRF guard (`safe_http.assert_public_url`) before
    the HTTP call, caps download size at :data:`_LOGO_MAX_BYTES`, and uses
    the shared httpx pool (see :mod:`webhook_service`).
    """
    # Import here to avoid a circular at module-import time.
    from app.services.webhook_service import get_http_client

    try:
        assert_public_url(url)
    except UnsafeTargetError as exc:
        log.info("qr_logo_blocked_ssrf url=%s reason=%s", url, exc)
        return None

    client = get_http_client()
    try:
        resp = await client.get(url, timeout=_LOGO_TIMEOUT)
        if resp.status_code >= 400:
            log.info("qr_logo_http_error url=%s status=%d", url, resp.status_code)
            return None
        buf = resp.content
        if len(buf) > _LOGO_MAX_BYTES:
            log.info(
                "qr_logo_too_large url=%s bytes=%d limit=%d",
                url,
                len(buf),
                _LOGO_MAX_BYTES,
            )
            return None
        return buf
    except Exception as exc:  # noqa: BLE001
        log.info("qr_logo_fetch_failed url=%s err=%s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Module drawer + color mask selection
# ---------------------------------------------------------------------------


def _module_drawer(kind: str | None):
    if kind == "rounded":
        return RoundedModuleDrawer()
    if kind == "extra-rounded":
        return CircleModuleDrawer()
    return SquareModuleDrawer()


def _validate_style(style: QRStyle | None) -> QRStyle:
    """Apply defaults, validate contrast. Returns a concrete QRStyle."""
    resolved = style.model_copy() if style is not None else QRStyle()
    fg = resolved.fg or _DEFAULT_FG
    bg = resolved.bg or _DEFAULT_BG
    if contrast_ratio(fg, bg) < 3.0:
        raise BadRequest(
            "QR contrast too low; scannable threshold 3:1",
            code="QR_LOW_CONTRAST",
        )
    resolved.fg = fg
    resolved.bg = bg
    return resolved


# ---------------------------------------------------------------------------
# PNG rendering
# ---------------------------------------------------------------------------


def _render_png_sync(
    content: str,
    style: QRStyle,
    size: int,
    logo_bytes: bytes | None,
) -> bytes:
    """Synchronous PIL pipeline — offloaded to a thread by the caller."""
    from PIL import Image  # local import: Pillow ships with qrcode[pil]

    fg = style.fg or _DEFAULT_FG
    bg = style.bg or _DEFAULT_BG
    fg_rgb = _hex_to_rgb(fg)
    bg_rgb = _hex_to_rgb(bg)

    # Higher error-correction so the logo overlay doesn't destroy scannability.
    ec = ERROR_CORRECT_H if logo_bytes else ERROR_CORRECT_M

    # Render at a modest internal box size (8px/module). The StyledPilImage
    # per-module drawers are CPU-hot, so we avoid oversizing the internal
    # bitmap and rely on a single LANCZOS upscale for final output.
    qr = qrcode.QRCode(
        version=None,
        error_correction=ec,
        box_size=8,
        border=2,
    )
    qr.add_data(content)
    qr.make(fit=True)

    styled_kwargs: dict[str, Any] = {
        "module_drawer": _module_drawer(style.dots),
        "color_mask": SolidFillColorMask(front_color=fg_rgb, back_color=bg_rgb),
    }
    img = qr.make_image(image_factory=StyledPilImage, **styled_kwargs)
    pil: "Image.Image" = img.get_image()  # type: ignore[assignment]
    pil = pil.convert("RGBA")

    # Final exact-size resize only when the pre-sized bitmap doesn't match.
    if size and pil.size[0] != size:
        pil = pil.resize((size, size), Image.LANCZOS)

    # Logo overlay (~20% of QR width). Requires ERC = H to stay scannable.
    if logo_bytes:
        try:
            logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
            target = int(size * 0.20)
            logo.thumbnail((target, target), Image.LANCZOS)
            # White padded backdrop — keeps the finder-pattern-less center
            # visually separated from surrounding modules.
            pad = 6
            backdrop = Image.new(
                "RGBA",
                (logo.size[0] + pad * 2, logo.size[1] + pad * 2),
                (*bg_rgb, 255),
            )
            backdrop.paste(logo, (pad, pad), mask=logo)
            pos = (
                (pil.size[0] - backdrop.size[0]) // 2,
                (pil.size[1] - backdrop.size[1]) // 2,
            )
            pil.alpha_composite(backdrop, dest=pos)
        except Exception as exc:  # noqa: BLE001
            log.info("qr_logo_paste_failed err=%s", exc)

    # Optional frame: expand canvas + redraw border.
    if style.frame and style.frame != "none":
        from PIL import ImageDraw

        pad = _FRAME_PADDING
        framed = Image.new(
            "RGBA",
            (pil.size[0] + pad * 2, pil.size[1] + pad * 2),
            (*bg_rgb, 255),
        )
        framed.alpha_composite(pil, dest=(pad, pad))
        draw = ImageDraw.Draw(framed)
        border_w = max(2, pad // 6)
        radius = pad if style.frame == "rounded" else 0
        draw.rounded_rectangle(
            (
                border_w // 2,
                border_w // 2,
                framed.size[0] - border_w // 2,
                framed.size[1] - border_w // 2,
            ),
            radius=radius,
            outline=(*fg_rgb, 255),
            width=border_w,
        )
        pil = framed

    out = io.BytesIO()
    pil.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()


# ---------------------------------------------------------------------------
# SVG rendering
# ---------------------------------------------------------------------------


def _render_svg(content: str, style: QRStyle, logo_bytes: bytes | None) -> bytes:
    """Produce a styled SVG.

    The ``qrcode.image.svg.SvgPathImage`` factory gives us a single ``<path>``
    for the modules — we rewrite its ``fill`` attribute and inject a
    background ``<rect>`` and (optionally) an ``<image>`` in the centre.

    All user-supplied values are XML-escaped before being written into the
    markup; we never f-string hex directly into raw SVG text.
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H if logo_bytes else ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(content)
    qr.make(fit=True)
    img: SvgPathImage = qr.make_image(image_factory=SvgPathImage)

    fg = xml_escape(style.fg or _DEFAULT_FG, {'"': "&quot;"})
    bg = xml_escape(style.bg or _DEFAULT_BG, {'"': "&quot;"})

    buf = io.BytesIO()
    img.save(buf)
    svg_bytes = buf.getvalue()
    svg = svg_bytes.decode("utf-8", errors="strict")

    # Inject background + recolour the modules path.
    svg = svg.replace(
        "<path ",
        f'<rect width="100%" height="100%" fill="{bg}"/><path ',
        1,
    )
    # SvgPathImage emits fill="#000000" on its path — rewrite it.
    svg = svg.replace('fill="#000000"', f'fill="{fg}"', 1)

    # Inline logo as data-URI, only if reasonably small.
    if logo_bytes and len(logo_bytes) <= _SVG_LOGO_MAX_BYTES:
        mime = _sniff_image_mime(logo_bytes) or "image/png"
        b64 = base64.b64encode(logo_bytes).decode("ascii")
        href = f"data:{mime};base64,{b64}"
        # Use percentage-based positioning; SVG viewBox is unit-agnostic.
        overlay = (
            '<image x="40%" y="40%" width="20%" height="20%" '
            f'preserveAspectRatio="xMidYMid meet" href="{xml_escape(href, {chr(34): "&quot;"})}"/>'
        )
        svg = svg.replace("</svg>", f"{overlay}</svg>", 1)
    elif logo_bytes:
        log.info(
            "qr_svg_logo_skipped_too_large bytes=%d limit=%d",
            len(logo_bytes),
            _SVG_LOGO_MAX_BYTES,
        )

    return svg.encode("utf-8")


def _sniff_image_mime(buf: bytes) -> str | None:
    if buf.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if buf.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if buf.startswith(b"GIF87a") or buf.startswith(b"GIF89a"):
        return "image/gif"
    if buf.startswith(b"<?xml") or buf.lstrip().startswith(b"<svg"):
        return "image/svg+xml"
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def generate_png(
    short_url: str,
    *,
    size: int = 512,
    style: QRStyle | None = None,
    url_id: UUID | None = None,
    redis: Any | None = None,
) -> bytes:
    """Render a branded PNG QR. Uses Redis cache when ``url_id`` + ``redis``
    are supplied."""
    resolved = _validate_style(style)
    cache_key = (
        f"qr:{url_id}:{style_hash(resolved)}:{size}:png"
        if url_id and redis is not None
        else None
    )
    # The shared cache_redis pool runs with ``decode_responses=True`` (see
    # ``redis_client.init_redis``) — we therefore base64-encode before
    # storing so binary PNG bytes roundtrip cleanly as text.
    if cache_key is not None:
        try:
            cached = await redis.get(cache_key)
            if cached:
                blob = cached if isinstance(cached, str) else cached.decode()
                return base64.b64decode(blob)
        except Exception as exc:  # noqa: BLE001
            log.info("qr_cache_read_failed key=%s err=%s", cache_key, exc)

    logo = await _fetch_logo(resolved.logo_url) if resolved.logo_url else None

    # Offload to a worker thread so PIL doesn't block the event loop for
    # larger sizes.
    import asyncio

    data = await asyncio.to_thread(_render_png_sync, short_url, resolved, size, logo)

    if cache_key is not None:
        try:
            await redis.set(
                cache_key,
                base64.b64encode(data).decode("ascii"),
                ex=_QR_CACHE_TTL_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001
            log.info("qr_cache_write_failed key=%s err=%s", cache_key, exc)

    return data


async def generate_svg(
    short_url: str,
    *,
    size: int = 512,  # noqa: ARG001 — reserved for future viewBox scaling
    style: QRStyle | None = None,
    url_id: UUID | None = None,  # noqa: ARG001 — accepted for symmetry
    redis: Any | None = None,  # noqa: ARG001
) -> bytes:
    """Render a branded SVG QR (no Redis caching; SVG generation is cheap)."""
    resolved = _validate_style(style)
    logo = await _fetch_logo(resolved.logo_url) if resolved.logo_url else None
    return _render_svg(short_url, resolved, logo)


# ---- Legacy helper (kept for backwards compatibility) --------------------


def make_qr(
    content: str, *, fmt: Format = "png", box_size: int = 10, border: int = 2
) -> tuple[bytes, str]:
    """Plain unstyled QR — used by code paths that haven't been migrated
    to :func:`generate_png` / :func:`generate_svg` yet."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(content)
    qr.make(fit=True)

    buf = io.BytesIO()
    if fmt == "svg":
        img: SvgImage = qr.make_image(image_factory=SvgImage)
        img.save(buf)
        return buf.getvalue(), "image/svg+xml"
    img_pil: PilImage = qr.make_image(fill_color="black", back_color="white")
    img_pil.save(buf, format="PNG")
    return buf.getvalue(), "image/png"
