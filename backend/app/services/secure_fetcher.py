"""Secure Fetcher (C2): the only code path allowed to make an outbound HTTP
request on behalf of Discovery.

Pipeline, revalidated on EVERY hop including redirects:

    URL syntax validation
          v
    DNS resolution (our own, once per hop)
          v
    IP safety validation (every resolved address)
          v
    HTTP(S) fetch, pinned to the validated IP
          v
    redirect? -> loop back to the top with the Location URL
          v
    size / content-type validation
          v
    FetchResult (caller turns this into a RawDocument)

No Evidence, Signal, Lead or Score is created here or reachable from here —
that boundary belongs to later chantiers (C3+).

DNS-rebinding defense: `resolve` and the actual connection happen against the
SAME validated IP literal within one hop — we never hand a bare hostname to
the HTTP transport and let it re-resolve behind our back. The request is sent
to the IP directly; `Host` and TLS SNI/certificate verification still target
the original hostname via httpx's `sni_hostname` extension, so this doesn't
weaken TLS in any way.
"""

from __future__ import annotations

import asyncio
import socket
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx

from app.core.config import settings
from app.core.network_safety import (
    DEFAULT_ALLOWED_PORTS,
    SecureFetchError,
    classify_ip,
    validate_url_syntax,
)

REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})

# Allowlist: only content we can meaningfully extract from later. Anything
# else (archives, executables, media, arbitrary octet-streams) is refused
# before the body is read to completion.
ALLOWED_CONTENT_TYPES = frozenset(
    {
        "text/html",
        "text/plain",
        "text/xml",
        "application/xhtml+xml",
        "application/json",
        "application/xml",
        "application/rss+xml",
        "application/atom+xml",
    }
)

Resolver = Callable[[str], Awaitable[list[str]]]


@dataclass
class RawHttpResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes
    resolved_ip: str


HttpGet = Callable[..., Awaitable[RawHttpResponse]]


@dataclass
class FetchResult:
    final_url: str
    status_code: int
    content_type: str | None
    body: bytes
    resolved_ip: str
    redirect_chain: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0


async def _default_resolve(hostname: str) -> list[str]:
    """Resolve a hostname to IP literals via the real system resolver.

    A hostname that is already an IP literal resolves to itself: getaddrinfo
    handles that natively without a DNS round-trip.
    """
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise SecureFetchError("dns_resolution_failed", str(exc)) from exc
    ips: list[str] = []
    for family, _type, _proto, _canon, sockaddr in infos:
        if family in (socket.AF_INET, socket.AF_INET6):
            ip = sockaddr[0]
            if ip not in ips:
                ips.append(ip)
    if not ips:
        raise SecureFetchError("dns_resolution_failed", f"no addresses for {hostname}")
    return ips


def _select_safe_ip(hostname: str, ips: list[str]) -> str:
    """Require every resolved address to be safe, then pick the first one.

    Rejecting the whole hostname if ANY resolved address is unsafe (rather
    than only skipping the bad ones) avoids a host that advertises both a
    public and a private/internal record from being partially trusted.
    """
    for ip in ips:
        reason = classify_ip(ip)
        if reason is not None:
            raise SecureFetchError(
                reason, f"{hostname} resolved to unsafe address {ip} ({reason})"
            )
    return ips[0]


async def _default_http_get(
    *,
    scheme: str,
    hostname: str,
    port: int,
    path_qs: str,
    resolved_ip: str,
    connect_timeout: float,
    read_timeout: float,
    max_bytes: int,
    user_agent: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> RawHttpResponse:
    """Fetch a single hop, pinned to `resolved_ip`, without following redirects.

    The connection target is the literal validated IP (never the hostname),
    so httpx/httpcore cannot silently re-resolve DNS between our validation
    and the actual TCP connect. `Host` and SNI still carry the real hostname
    for correct virtual hosting and certificate verification.

    `transport` is injectable so tests can exercise this exact code path
    (URL/header construction, streaming size cap, response parsing) against
    an `httpx.MockTransport` instead of real sockets. Production leaves it
    unset and gets the real network transport.
    """
    ip_for_url = f"[{resolved_ip}]" if ":" in resolved_ip else resolved_ip
    pinned_url = f"{scheme}://{ip_for_url}:{port}{path_qs}"
    timeout = httpx.Timeout(
        connect=connect_timeout, read=read_timeout, write=read_timeout, pool=connect_timeout
    )
    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=False, verify=True, transport=transport
    ) as client:
        request = client.build_request(
            "GET",
            pinned_url,
            headers={"Host": hostname, "User-Agent": user_agent, "Accept-Encoding": "identity"},
        )
        if scheme == "https":
            request.extensions["sni_hostname"] = hostname
        response = await client.send(request, stream=True)
        try:
            body = b""
            async for chunk in response.aiter_bytes():
                body += chunk
                if len(body) > max_bytes:
                    raise SecureFetchError(
                        "response_too_large", f"exceeded {max_bytes} bytes while streaming"
                    )
        finally:
            await response.aclose()
        return RawHttpResponse(
            status_code=response.status_code,
            headers={k.lower(): v for k, v in response.headers.items()},
            body=body,
            resolved_ip=resolved_ip,
        )


def _content_type_allowed(content_type: str | None) -> bool:
    if content_type is None:
        return True  # absence of a header is not itself grounds for rejection
    base = content_type.split(";", 1)[0].strip().lower()
    return base in ALLOWED_CONTENT_TYPES


async def secure_fetch(
    url: str,
    *,
    resolver: Resolver | None = None,
    http_get: HttpGet | None = None,
    max_redirects: int | None = None,
    max_bytes: int | None = None,
    connect_timeout: float | None = None,
    read_timeout: float | None = None,
    total_timeout: float | None = None,
    allowed_ports: frozenset[int] | None = None,
    user_agent: str | None = None,
) -> FetchResult:
    """Fetch `url` under full SSRF protection, following redirects safely.

    `resolver` and `http_get` are injectable so tests can exercise the full
    redirect/validation state machine deterministically, with no real DNS or
    sockets involved. Production code paths use the real implementations by
    default.
    """
    resolve = resolver or _default_resolve
    do_get = http_get or _default_http_get
    cfg = settings
    if max_redirects is None:
        max_redirects = cfg.discovery_fetch_max_redirects
    if max_bytes is None:
        max_bytes = cfg.discovery_fetch_max_bytes
    if connect_timeout is None:
        connect_timeout = cfg.discovery_fetch_connect_timeout
    if read_timeout is None:
        read_timeout = cfg.discovery_fetch_read_timeout
    if total_timeout is None:
        total_timeout = cfg.discovery_fetch_total_timeout
    if user_agent is None:
        user_agent = cfg.discovery_fetch_user_agent
    if allowed_ports is None:
        allowed_ports = DEFAULT_ALLOWED_PORTS

    started = time.monotonic()
    current_url = url
    redirect_chain: list[str] = []

    for hop in range(max_redirects + 1):
        if time.monotonic() - started > total_timeout:
            raise SecureFetchError("timeout", "total fetch timeout exceeded")

        target = validate_url_syntax(current_url, allowed_ports=allowed_ports)
        ips = await resolve(target.hostname)
        safe_ip = _select_safe_ip(target.hostname, ips)

        response = await do_get(
            scheme=target.scheme,
            hostname=target.hostname,
            port=target.port,
            path_qs=target.path_qs,
            resolved_ip=safe_ip,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            max_bytes=max_bytes,
            user_agent=user_agent,
        )

        if response.status_code in REDIRECT_STATUS_CODES:
            location = response.headers.get("location")
            if not location:
                raise SecureFetchError("malformed_redirect", "redirect without Location header")
            next_url = urljoin(current_url, location)
            redirect_chain.append(current_url)
            if hop >= max_redirects:
                raise SecureFetchError(
                    "too_many_redirects", f"exceeded {max_redirects} redirects"
                )
            current_url = next_url
            continue

        content_type = response.headers.get("content-type")
        if not _content_type_allowed(content_type):
            raise SecureFetchError(
                "blocked_content_type", f"content-type {content_type!r} is not allowed"
            )

        return FetchResult(
            final_url=current_url,
            status_code=response.status_code,
            content_type=content_type,
            body=response.body,
            resolved_ip=response.resolved_ip,
            redirect_chain=redirect_chain,
            elapsed_seconds=time.monotonic() - started,
        )

    raise SecureFetchError("too_many_redirects", f"exceeded {max_redirects} redirects")
