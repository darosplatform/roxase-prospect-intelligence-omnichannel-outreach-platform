"""Discovery helpers: content/dedup hashing.

C1 does no network I/O; these helpers canonicalize and hash candidate URLs and
targets so jobs/sources can be deduplicated deterministically across a tenant.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_url(url: str) -> str:
    """Lowercase scheme/host, strip default ports, drop fragment, trim trailing slash."""
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    query = parsed.query
    fragment = ""
    _default_port = (
        scheme == "http" and parsed.port == 80
        or scheme == "https" and parsed.port == 443
    )
    if parsed.port and _default_port:
        host = parsed.hostname or host
    netloc = host
    if parsed.username:
        netloc = f"{parsed.username}@{host}"
    rebuilt = f"{scheme}://{netloc}{path}"
    if query:
        rebuilt += f"?{query}"
    if fragment:
        rebuilt += f"#{fragment}"
    return rebuilt


_URL_HASH_RE = re.compile(r"[:/?#]")  # sanity anchor for tests


def url_hash(url: str) -> str:
    return sha256_hex(_canonical_url(url))


def target_hash(target: str) -> str:
    """Hash a job target (e.g. domain or URL descriptor) canonically."""
    canonical = _canonical_url(target) if "://" in target else target.strip().lower()
    return sha256_hex(canonical)


def content_hash(body: str) -> str:
    return sha256_hex(body)