"""SSRF guardrails for outbound HTTP (webhook dispatch etc.).

RV10 1.4: webhook targets are user-supplied URLs. Without validation,
`httpx.AsyncClient.post(url)` can reach Postgres/Redis on the shared Docker
network, the cloud-provider metadata endpoint (``169.254.169.254``), or
anything bound on ``127.0.0.1`` inside the API container.

This module resolves the hostname and rejects any result that is private,
loopback, link-local, multicast, or otherwise reserved. It is intentionally
strict — DNS rebinding is still a concern, so callers should invoke
:func:`assert_public_url` BOTH on write (to reject obviously bad targets at
ingestion) AND immediately before the actual HTTP call (to close the
time-of-check/time-of-use gap).
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeTargetError(ValueError):
    """Raised when the target URL resolves to a non-public address."""


def _ip_is_public(ip: ipaddress._BaseAddress) -> bool:
    """Mirror ``ipaddress.ip_address.is_global`` but with explicit checks.

    We prefer named checks so the error message can name which rule fired.
    """
    if ip.is_loopback:
        return False
    if ip.is_private:
        return False
    if ip.is_link_local:
        return False
    if ip.is_multicast:
        return False
    if ip.is_reserved:
        return False
    if ip.is_unspecified:
        return False
    return True


def assert_public_url(url: str) -> None:
    """Raise :class:`UnsafeTargetError` unless ``url`` resolves to a public IP.

    Accepts only ``http`` / ``https`` schemes with an explicit hostname.
    Every address returned by ``getaddrinfo`` must pass — it is not enough
    for ONE record to be public when the resolver may return multiple.
    """
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeTargetError(
            f"unsupported scheme {parsed.scheme!r}; only http(s) is allowed"
        )
    host = parsed.hostname
    if not host:
        raise UnsafeTargetError("URL is missing a hostname")

    # Reject bracketed-IPv6 / raw IPs that self-identify as private without
    # a DNS round-trip — also covers hosts files spoofing.
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not _ip_is_public(literal):
        raise UnsafeTargetError(
            f"refusing non-public literal address {host!r}"
        )

    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeTargetError(f"DNS resolution failed for {host!r}") from exc

    if not infos:
        raise UnsafeTargetError(f"no addresses resolved for {host!r}")

    for family, _type, _proto, _canon, sockaddr in infos:
        ip_str = sockaddr[0]
        # IPv6 scope suffixes (e.g. ``fe80::1%eth0``) break ip_address().
        if isinstance(ip_str, str) and "%" in ip_str:
            ip_str = ip_str.split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            raise UnsafeTargetError(
                f"resolver returned uninterpretable address {ip_str!r} for "
                f"{host!r}"
            )
        if not _ip_is_public(ip):
            raise UnsafeTargetError(
                f"refusing private/reserved address {ip} for host {host!r}"
            )
