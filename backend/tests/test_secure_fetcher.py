"""C2 Secure Fetcher / SSRF test suite.

Entirely network-free and deterministic: DNS resolution and the HTTP
transport are both injectable, so every scenario (public fetch, redirects,
SSRF blocks, DNS rebinding, timeouts, size/content-type limits) is exercised
without a single real socket. `_default_http_get` itself is also exercised
directly via `httpx.MockTransport`, so the real streaming/size-cap/IP-pinning
code path gets genuine coverage, not just the orchestration around it.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.core.network_safety import SecureFetchError, classify_ip, validate_url_syntax
from app.services.secure_fetcher import (
    RawHttpResponse,
    _default_http_get,
    secure_fetch,
)

PUBLIC_V4 = "93.184.216.34"
PUBLIC_V4_ALT = "8.8.8.8"
PUBLIC_V6 = "2001:4860:4860::8888"


# --------------------------------------------------------------------------- #
# classify_ip: pure IP classification, no I/O
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("ip", [PUBLIC_V4, PUBLIC_V4_ALT, PUBLIC_V6])
def test_classify_ip_public_is_safe(ip):
    assert classify_ip(ip) is None


def test_classify_ip_loopback_v4():
    assert classify_ip("127.0.0.1") == "blocked_loopback"


def test_classify_ip_loopback_v6():
    assert classify_ip("::1") == "blocked_loopback"


@pytest.mark.parametrize("ip", ["10.0.0.1", "172.16.5.5", "172.31.255.254", "192.168.1.1"])
def test_classify_ip_rfc1918_blocked(ip):
    assert classify_ip(ip) == "blocked_private"


def test_classify_ip_link_local_v4():
    assert classify_ip("169.254.1.1") == "blocked_link_local"


def test_classify_ip_link_local_v6():
    assert classify_ip("fe80::1") == "blocked_link_local"


@pytest.mark.parametrize("ip", ["224.0.0.1", "ff02::1"])
def test_classify_ip_multicast_blocked(ip):
    assert classify_ip(ip) == "blocked_multicast"


@pytest.mark.parametrize("ip", ["0.0.0.0", "::"])
def test_classify_ip_unspecified_blocked(ip):
    assert classify_ip(ip) == "blocked_unspecified"


def test_classify_ip_cloud_metadata_blocked():
    assert classify_ip("169.254.169.254") == "blocked_cloud_metadata"
    assert classify_ip("100.100.100.200") == "blocked_cloud_metadata"


def test_classify_ip_ipv6_unique_local_blocked():
    assert classify_ip("fd12:3456:789a::1") == "blocked_private"


def test_classify_ip_ipv4_mapped_ipv6_loopback_blocked():
    # ::ffff:127.0.0.1 must be judged by its embedded IPv4 form.
    assert classify_ip("::ffff:127.0.0.1") == "blocked_loopback"


def test_classify_ip_invalid_literal():
    assert classify_ip("not-an-ip") == "invalid_ip"


# --------------------------------------------------------------------------- #
# validate_url_syntax: scheme/port/hostname shape, no I/O
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/",
        "gopher://example.com/",
        "data:text/plain;base64,aGVsbG8=",
        "javascript:alert(1)",
    ],
)
def test_validate_url_syntax_rejects_disallowed_schemes(url):
    with pytest.raises(SecureFetchError) as exc:
        validate_url_syntax(url)
    assert exc.value.code == "blocked_scheme"


def test_validate_url_syntax_rejects_missing_hostname():
    with pytest.raises(SecureFetchError) as exc:
        validate_url_syntax("http:///just/a/path")
    assert exc.value.code == "malformed_url"


def test_validate_url_syntax_rejects_empty():
    with pytest.raises(SecureFetchError) as exc:
        validate_url_syntax("")
    assert exc.value.code == "malformed_url"


def test_validate_url_syntax_rejects_disallowed_port():
    with pytest.raises(SecureFetchError) as exc:
        validate_url_syntax("http://example.com:8080/")
    assert exc.value.code == "blocked_port"


def test_validate_url_syntax_allows_default_ports():
    t = validate_url_syntax("http://example.com/a")
    assert t.port == 80
    t = validate_url_syntax("https://example.com/a")
    assert t.port == 443


# --------------------------------------------------------------------------- #
# secure_fetch orchestration: fake resolver + fake http_get, per-hop safety
# --------------------------------------------------------------------------- #


def make_resolver(host_ips: dict[str, list[str]], call_log: list[str] | None = None):
    async def _resolve(hostname: str) -> list[str]:
        if call_log is not None:
            call_log.append(hostname)
        if hostname not in host_ips:
            raise SecureFetchError("dns_resolution_failed", f"no mapping for {hostname}")
        return host_ips[hostname]

    return _resolve


def make_http_get(responses: dict[str, RawHttpResponse], resolved_ip_log: list[str] | None = None):
    """responses is keyed by hostname; the fake never looks at the network."""

    async def _get(*, hostname, resolved_ip, **_kwargs) -> RawHttpResponse:
        if resolved_ip_log is not None:
            resolved_ip_log.append(resolved_ip)
        if hostname not in responses:
            raise AssertionError(f"unexpected fetch for {hostname}")
        resp = responses[hostname]
        return RawHttpResponse(
            status_code=resp.status_code,
            headers=resp.headers,
            body=resp.body,
            resolved_ip=resolved_ip,
        )

    return _get


@pytest.mark.asyncio
async def test_fetch_public_http_allowed():
    resolver = make_resolver({"news.example": [PUBLIC_V4]})
    http_get = make_http_get(
        {
            "news.example": RawHttpResponse(
                200, {"content-type": "text/html"}, b"<html>ok</html>", PUBLIC_V4
            )
        }
    )
    result = await secure_fetch(
        "http://news.example/page", resolver=resolver, http_get=http_get
    )
    assert result.status_code == 200
    assert result.body == b"<html>ok</html>"
    assert result.resolved_ip == PUBLIC_V4


@pytest.mark.asyncio
async def test_fetch_public_https_allowed():
    resolver = make_resolver({"news.example": [PUBLIC_V6]})
    http_get = make_http_get(
        {
            "news.example": RawHttpResponse(
                200, {"content-type": "application/json"}, b"{}", PUBLIC_V6
            )
        }
    )
    result = await secure_fetch(
        "https://news.example/api", resolver=resolver, http_get=http_get
    )
    assert result.status_code == 200
    assert result.resolved_ip == PUBLIC_V6


@pytest.mark.asyncio
async def test_fetch_localhost_blocked():
    resolver = make_resolver({"localhost": ["127.0.0.1"]})
    with pytest.raises(SecureFetchError) as exc:
        await secure_fetch("http://localhost/admin", resolver=resolver, http_get=make_http_get({}))
    assert exc.value.code == "blocked_loopback"


@pytest.mark.asyncio
async def test_fetch_rfc1918_blocked():
    resolver = make_resolver({"internal.example": ["10.1.2.3"]})
    with pytest.raises(SecureFetchError) as exc:
        await secure_fetch(
            "http://internal.example/", resolver=resolver, http_get=make_http_get({})
        )
    assert exc.value.code == "blocked_private"


@pytest.mark.asyncio
async def test_fetch_link_local_blocked():
    resolver = make_resolver({"h.example": ["169.254.1.1"]})
    with pytest.raises(SecureFetchError) as exc:
        await secure_fetch("http://h.example/", resolver=resolver, http_get=make_http_get({}))
    assert exc.value.code == "blocked_link_local"


@pytest.mark.asyncio
async def test_fetch_multicast_blocked():
    resolver = make_resolver({"h.example": ["224.0.0.5"]})
    with pytest.raises(SecureFetchError) as exc:
        await secure_fetch("http://h.example/", resolver=resolver, http_get=make_http_get({}))
    assert exc.value.code == "blocked_multicast"


@pytest.mark.asyncio
async def test_fetch_ipv6_loopback_blocked():
    resolver = make_resolver({"h.example": ["::1"]})
    with pytest.raises(SecureFetchError) as exc:
        await secure_fetch("http://h.example/", resolver=resolver, http_get=make_http_get({}))
    assert exc.value.code == "blocked_loopback"


@pytest.mark.asyncio
async def test_fetch_ipv6_link_local_blocked():
    resolver = make_resolver({"h.example": ["fe80::1"]})
    with pytest.raises(SecureFetchError) as exc:
        await secure_fetch("http://h.example/", resolver=resolver, http_get=make_http_get({}))
    assert exc.value.code == "blocked_link_local"


@pytest.mark.asyncio
async def test_fetch_cloud_metadata_blocked():
    resolver = make_resolver({"h.example": ["169.254.169.254"]})
    with pytest.raises(SecureFetchError) as exc:
        await secure_fetch("http://h.example/", resolver=resolver, http_get=make_http_get({}))
    assert exc.value.code == "blocked_cloud_metadata"


@pytest.mark.asyncio
async def test_fetch_disallowed_port_blocked():
    with pytest.raises(SecureFetchError) as exc:
        await secure_fetch(
            "http://h.example:8080/",
            resolver=make_resolver({"h.example": [PUBLIC_V4]}),
            http_get=make_http_get({}),
        )
    assert exc.value.code == "blocked_port"


@pytest.mark.asyncio
async def test_fetch_disallowed_scheme_blocked():
    with pytest.raises(SecureFetchError) as exc:
        await secure_fetch(
            "ftp://h.example/",
            resolver=make_resolver({"h.example": [PUBLIC_V4]}),
            http_get=make_http_get({}),
        )
    assert exc.value.code == "blocked_scheme"


@pytest.mark.asyncio
async def test_dns_resolution_failure_raises():
    resolver = make_resolver({})  # no mapping -> resolver raises
    with pytest.raises(SecureFetchError) as exc:
        await secure_fetch(
            "http://missing.example/", resolver=resolver, http_get=make_http_get({})
        )
    assert exc.value.code == "dns_resolution_failed"


@pytest.mark.asyncio
async def test_redirect_public_to_public_allowed():
    resolver = make_resolver(
        {"a.example": [PUBLIC_V4], "b.example": [PUBLIC_V4_ALT]}
    )
    http_get = make_http_get(
        {
            "a.example": RawHttpResponse(
                302, {"location": "https://b.example/final"}, b"", PUBLIC_V4
            ),
            "b.example": RawHttpResponse(
                200, {"content-type": "text/html"}, b"final page", PUBLIC_V4_ALT
            ),
        }
    )
    result = await secure_fetch(
        "https://a.example/start", resolver=resolver, http_get=http_get
    )
    assert result.status_code == 200
    assert result.final_url == "https://b.example/final"
    assert result.redirect_chain == ["https://a.example/start"]


@pytest.mark.asyncio
async def test_redirect_public_to_private_blocked():
    """The classic SSRF-via-redirect attack: a safe host redirects to a
    private one. Each hop must be revalidated independently."""
    resolver = make_resolver(
        {"a.example": [PUBLIC_V4], "internal.example": ["192.168.0.5"]}
    )
    http_get = make_http_get(
        {
            "a.example": RawHttpResponse(
                302, {"location": "http://internal.example/secret"}, b"", PUBLIC_V4
            ),
        }
    )
    with pytest.raises(SecureFetchError) as exc:
        await secure_fetch("http://a.example/start", resolver=resolver, http_get=http_get)
    assert exc.value.code == "blocked_private"


@pytest.mark.asyncio
async def test_redirect_chain_excessive_blocked():
    host_ips = {f"h{i}.example": [PUBLIC_V4] for i in range(10)}
    responses = {}
    for i in range(9):
        responses[f"h{i}.example"] = RawHttpResponse(
            302, {"location": f"http://h{i + 1}.example/"}, b"", PUBLIC_V4
        )
    responses["h9.example"] = RawHttpResponse(200, {"content-type": "text/html"}, b"ok", PUBLIC_V4)
    resolver = make_resolver(host_ips)
    http_get = make_http_get(responses)
    with pytest.raises(SecureFetchError) as exc:
        await secure_fetch(
            "http://h0.example/", resolver=resolver, http_get=http_get, max_redirects=3
        )
    assert exc.value.code == "too_many_redirects"


@pytest.mark.asyncio
async def test_response_too_large_propagated():
    async def oversized_get(**_kwargs):
        raise SecureFetchError("response_too_large", "exceeded cap while streaming")

    with pytest.raises(SecureFetchError) as exc:
        await secure_fetch(
            "http://h.example/",
            resolver=make_resolver({"h.example": [PUBLIC_V4]}),
            http_get=oversized_get,
        )
    assert exc.value.code == "response_too_large"


@pytest.mark.asyncio
async def test_blocked_content_type():
    resolver = make_resolver({"h.example": [PUBLIC_V4]})
    http_get = make_http_get(
        {
            "h.example": RawHttpResponse(
                200, {"content-type": "application/x-executable"}, b"MZ...", PUBLIC_V4
            )
        }
    )
    with pytest.raises(SecureFetchError) as exc:
        await secure_fetch("http://h.example/", resolver=resolver, http_get=http_get)
    assert exc.value.code == "blocked_content_type"


@pytest.mark.asyncio
async def test_total_timeout_exceeded():
    async def slow_resolver(hostname):
        await asyncio.sleep(0.05)
        return [PUBLIC_V4]

    http_get = make_http_get(
        {
            "a.example": RawHttpResponse(
                302, {"location": "http://b.example/"}, b"", PUBLIC_V4
            ),
        }
    )
    with pytest.raises(SecureFetchError) as exc:
        await secure_fetch(
            "http://a.example/",
            resolver=slow_resolver,
            http_get=http_get,
            total_timeout=0.01,
        )
    assert exc.value.code == "timeout"


@pytest.mark.asyncio
async def test_dns_rebinding_resolution_happens_once_per_hop_and_is_pinned():
    """Even if the underlying resolver would answer differently on a second
    call (a very-short-TTL rebinding attacker), secure_fetch must resolve a
    hostname exactly once per hop and connect to that exact validated IP —
    never re-resolve behind the safety check's back."""
    call_log: list[str] = []
    resolved_ip_log: list[str] = []

    answers = iter([[PUBLIC_V4], ["10.0.0.9"]])  # 2nd answer would be unsafe

    async def rebinding_resolver(hostname):
        call_log.append(hostname)
        return next(answers)

    http_get = make_http_get(
        {"a.example": RawHttpResponse(200, {"content-type": "text/html"}, b"ok", PUBLIC_V4)},
        resolved_ip_log=resolved_ip_log,
    )
    result = await secure_fetch(
        "http://a.example/", resolver=rebinding_resolver, http_get=http_get
    )
    assert result.status_code == 200
    # Resolved exactly once for this single-hop fetch, and the connection used
    # that first (safe) answer — not a second, potentially-rebound one.
    assert call_log == ["a.example"]
    assert resolved_ip_log == [PUBLIC_V4]


# --------------------------------------------------------------------------- #
# _default_http_get via httpx.MockTransport: real streaming/size-cap/IP-pin
# code path, still with zero real sockets.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_default_http_get_pins_connection_to_resolved_ip():
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url_host"] = request.url.host
        seen["host_header"] = request.headers.get("host")
        seen["sni"] = request.extensions.get("sni_hostname")
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"hi")

    transport = httpx.MockTransport(handler)
    resp = await _default_http_get(
        scheme="https",
        hostname="news.example",
        port=443,
        path_qs="/a",
        resolved_ip=PUBLIC_V4,
        connect_timeout=1.0,
        read_timeout=1.0,
        max_bytes=1000,
        user_agent="test-agent",
        transport=transport,
    )
    assert resp.status_code == 200
    assert resp.body == b"hi"
    # The wire-level connection target is the validated IP, not the hostname;
    # Host + SNI still carry the real hostname (correct vhosting + cert check).
    assert seen["url_host"] == PUBLIC_V4
    assert seen["host_header"] == "news.example"
    assert seen["sni"] == "news.example"


@pytest.mark.asyncio
async def test_default_http_get_enforces_size_cap_while_streaming():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/html"}, content=b"x" * 10_000
        )

    transport = httpx.MockTransport(handler)
    with pytest.raises(SecureFetchError) as exc:
        await _default_http_get(
            scheme="http",
            hostname="h.example",
            port=80,
            path_qs="/",
            resolved_ip=PUBLIC_V4,
            connect_timeout=1.0,
            read_timeout=1.0,
            max_bytes=100,
            user_agent="test-agent",
            transport=transport,
        )
    assert exc.value.code == "response_too_large"


@pytest.mark.asyncio
async def test_default_http_get_reports_content_type_for_blocking():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "application/zip"}, content=b"PK\x03\x04"
        )

    transport = httpx.MockTransport(handler)
    resp = await _default_http_get(
        scheme="http",
        hostname="h.example",
        port=80,
        path_qs="/",
        resolved_ip=PUBLIC_V4,
        connect_timeout=1.0,
        read_timeout=1.0,
        max_bytes=1000,
        user_agent="test-agent",
        transport=transport,
    )
    # _default_http_get itself doesn't enforce the allowlist (secure_fetch
    # does, after the hop completes) — confirm the header is surfaced intact
    # so the caller's check has something real to act on.
    assert resp.headers["content-type"] == "application/zip"
