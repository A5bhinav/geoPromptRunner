"""Guard outbound HTTP against SSRF.

This tool fetches user-influenced URLs (client domains for technical checks,
grounding-citation redirects). Without a guard, a crafted URL could point the
server at internal services or the cloud metadata endpoint
(``169.254.169.254``). ``assert_public_url`` rejects non-http(s) schemes and any
host that resolves to a private / loopback / link-local / reserved address, and
``safe_get`` follows redirects manually so every hop is re-validated (auto
follow-redirects would let a public URL bounce to an internal one).

Best-effort: this validates at resolution time, not per-connection, so it does
not defeat a determined DNS-rebind. It does stop the common cases (metadata IP,
localhost, RFC-1918, link-local) that matter for a tool fed user domains.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

__all__ = ["UnsafeUrlError", "assert_public_url", "safe_get"]

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_MAX_REDIRECTS = 5


class UnsafeUrlError(ValueError):
    """Raised when a URL's scheme or resolved host is not a safe public target."""


def _ip_is_public(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def assert_public_url(url: str) -> None:
    """Raise ``UnsafeUrlError`` unless ``url`` is http(s) to a public host.

    Every address the host resolves to must be public — a host with even one
    private A/AAAA record is rejected.
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"scheme not allowed: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise UnsafeUrlError("URL has no host")
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"could not resolve host {host!r}") from exc
    ips = {str(info[4][0]) for info in infos}
    if not ips:
        raise UnsafeUrlError(f"host {host!r} resolved to no addresses")
    for ip in ips:
        if not _ip_is_public(ip):
            raise UnsafeUrlError(f"host {host!r} resolves to non-public address {ip}")


def safe_get(
    client: httpx.Client,
    url: str,
    *,
    max_redirects: int = _MAX_REDIRECTS,
    **kwargs: object,
) -> httpx.Response:
    """GET ``url`` following redirects manually, validating every hop.

    Each location (initial and every redirect target) must pass
    ``assert_public_url`` before the request is made, so a public URL can't
    redirect the server into an internal one. Raises ``UnsafeUrlError`` on any
    unsafe hop and ``httpx.HTTPError`` on transport errors.
    """
    current = url
    for _ in range(max_redirects + 1):
        assert_public_url(current)
        response = client.get(current, follow_redirects=False, **kwargs)  # type: ignore[arg-type]
        if response.is_redirect and "location" in response.headers:
            current = str(response.url.join(response.headers["location"]))
            continue
        return response
    raise UnsafeUrlError(f"too many redirects from {url}")
