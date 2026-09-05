"""SSRF safety primitives: URL syntax rules and IP-address classification.

Pure, network-free logic so it can be unit tested deterministically and reused
by both the secure fetcher (C2) and anything else that needs to answer "is it
safe to connect to this address" (e.g. a future webhook sender). Nothing here
performs I/O: DNS resolution and the actual fetch live in
`app.services.secure_fetcher`.

The rule is IP-based, never hostname-based: a hostname is only as safe as the
address it resolves to *right now*. Callers must resolve first, then check
every returned address with `classify_ip` before connecting to any of them.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit

ALLOWED_SCHEMES = frozenset({"http", "https"})
DEFAULT_ALLOWED_PORTS = frozenset({80, 443})

# Known cloud metadata endpoints. Most are already covered by the link-local
# check (169.254.0.0/16) but are listed explicitly so the block reason is
# unambiguous and survives any future change to the link-local rule.
CLOUD_METADATA_IPS = frozenset(
    {
        "169.254.169.254",  # AWS / GCP / Azure / DigitalOcean / OpenStack
        "169.254.170.2",  # AWS ECS task metadata
        "100.100.100.200",  # Alibaba Cloud
        "fd00:ec2::254",  # AWS IMDSv2 (IPv6)
    }
)


class SecureFetchError(Exception):
    """Raised whenever a URL or resolved address fails a safety check."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class ParsedTarget:
    scheme: str
    hostname: str
    port: int
    path_qs: str  # path + "?" + query, always starts with "/"


def validate_url_syntax(
    url: str, *, allowed_ports: frozenset[int] = DEFAULT_ALLOWED_PORTS
) -> ParsedTarget:
    """Validate scheme/host/port shape. Raises SecureFetchError on any violation.

    Does NOT touch the network and does NOT decide IP safety — only that the
    URL is well-formed and uses an explicitly allowed scheme/port.
    """
    if not url or not isinstance(url, str):
        raise SecureFetchError("malformed_url", "empty or non-string URL")
    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise SecureFetchError("blocked_scheme", f"scheme {scheme!r} is not http/https")
    if not parsed.hostname:
        raise SecureFetchError("malformed_url", "missing hostname")
    hostname = parsed.hostname
    try:
        port = parsed.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise SecureFetchError("malformed_url", "invalid port") from exc
    if port not in allowed_ports:
        raise SecureFetchError("blocked_port", f"port {port} is not allowed")
    path_qs = parsed.path or "/"
    if parsed.query:
        path_qs += f"?{parsed.query}"
    return ParsedTarget(scheme=scheme, hostname=hostname, port=port, path_qs=path_qs)


def classify_ip(address: str) -> str | None:
    """Return a block-reason code for an unsafe IP, or None if it is safe.

    Pure classification: takes a single already-resolved IP literal (v4 or
    v6). Never accepts a hostname. Every reason is specific so tests and logs
    can distinguish e.g. loopback from RFC1918.
    """
    if address in CLOUD_METADATA_IPS:
        return "blocked_cloud_metadata"
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return "invalid_ip"

    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        # ::ffff:127.0.0.1 style mapped addresses must be judged as their v4 form.
        mapped = classify_ip(str(ip.ipv4_mapped))
        if mapped is not None:
            return mapped

    if ip.is_loopback:
        return "blocked_loopback"
    if ip.is_link_local:
        return "blocked_link_local"
    if ip.is_multicast:
        return "blocked_multicast"
    if ip.is_unspecified:
        return "blocked_unspecified"
    if ip.is_reserved:
        return "blocked_reserved"
    if ip.is_private:
        return "blocked_private"
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.is_site_local:  # legacy fec0::/10
            return "blocked_site_local"
        # Unique local addresses (fc00::/7, includes fd00::/8) are already
        # covered by `is_private` in Python's ipaddress, kept here as a
        # defensive, explicit double-check in case that ever changes.
        if ip in ipaddress.ip_network("fc00::/7"):
            return "blocked_unique_local"
    return None
