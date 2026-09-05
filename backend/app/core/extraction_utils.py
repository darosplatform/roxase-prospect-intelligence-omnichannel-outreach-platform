"""Extraction/normalization primitives (C3): pure, network-free, deterministic.

Nothing here parses HTML — that lives in `app.services.extraction`, which
depends on these helpers. Keeping the regex/normalization rules here means
they can be unit tested directly, without a document or a database.

The governing rule (from ROXASE's own principle): never turn an inference
into a fact. These helpers only ever report what they actually found in the
text — they do not guess a name from an email's local part, do not invent a
missing field, and do not upgrade confidence based on a pattern that merely
"looks right".
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit

# A conservative RFC 5322-ish match: good enough to find real-looking emails
# in free text without accepting garbage. Intentionally stricter than the
# full RFC grammar (no quoted strings, no comments) since those almost never
# appear in scraped marketing/about pages and mostly signal noise.
#  The trailing lookahead only excludes an immediately-following alnum char
#  (not '.'/'+'/'-'), so a real address glued to sentence-final punctuation
#  ("...at jane@acme.com.") still matches in full instead of failing outright.
_EMAIL_RE = re.compile(
    r"(?<![\w.+-])[A-Za-z0-9][A-Za-z0-9._%+-]{0,63}@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+(?![A-Za-z0-9])"
)

# Free public webmail domains are never "professional" evidence of a company
# even when the surrounding page is a company site — flagged, not upgraded.
_PUBLIC_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "yahoo.com",
        "hotmail.com",
        "outlook.com",
        "aol.com",
        "icloud.com",
        "protonmail.com",
        "gmx.com",
        "mail.com",
        "live.com",
    }
)

# A phone candidate: optional leading +, then digits/separators, at least 7
# significant digits (loose international heuristic — not a full E.164
# validator; we only ever report a normalized candidate, never claim it's
# dialable).
_PHONE_RE = re.compile(r"(?<!\w)(\+?\d[\d\s().-]{6,}\d)(?!\w)")

_JOB_TITLE_KEYWORDS = (
    "chief executive officer",
    "chief technology officer",
    "chief financial officer",
    "chief operating officer",
    "ceo",
    "cto",
    "cfo",
    "coo",
    "founder",
    "co-founder",
    "president",
    "vice president",
    "vp ",
    "director",
    "head of",
    "manager",
    "lead ",
    "engineer",
    "designer",
    "partner",
)

_LEGAL_SUFFIXES = (
    " inc",
    " inc.",
    " llc",
    " l.l.c.",
    " ltd",
    " ltd.",
    " limited",
    " corp",
    " corp.",
    " corporation",
    " co.",
    " gmbh",
    " sarl",
    " sas",
    " sa",
    " plc",
    " ag",
)

# URL-path / title keyword -> page type. Order matters: first match wins, so
# more specific buckets are listed before generic ones.
_PAGE_TYPE_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("leadership", "leadership"),
    ("management", "leadership"),
    ("team", "team"),
    ("careers", "careers"),
    ("jobs", "careers"),
    ("contact", "contact"),
    ("about", "about"),
    ("product", "products"),
    ("pricing", "products"),
    ("news", "news"),
    ("blog", "news"),
    ("press", "press"),
    ("media", "press"),
    ("partner", "partnerships"),
)


def classify_page(url: str, title: str | None = None) -> str:
    """Classify a fetched page from its URL path and title (deterministic
    keyword match — no ML, no guessing). Returns "other" when nothing
    matches."""
    haystack = urlsplit(url).path.lower()
    if title:
        haystack += " " + title.lower()
    for keyword, page_type in _PAGE_TYPE_KEYWORDS:
        if keyword in haystack:
            return page_type
    return "other"


def find_emails(text: str) -> list[str]:
    """Return every syntactically valid email literal found in `text`,
    de-duplicated, order preserved. Does not validate deliverability — only
    that the candidate has valid email syntax."""
    seen: list[str] = []
    for match in _EMAIL_RE.finditer(text):
        candidate = match.group(0)
        if candidate not in seen:
            seen.append(candidate)
    return seen


def is_professional_email(email: str, company_domain: str | None) -> bool:
    """True only when the email's domain matches the company's own domain.

    A free-webmail address is never professional evidence, even if found on
    the company's own site (e.g. a personal contact left in a footer). An
    email at some OTHER company's domain is not evidence of employment here
    either — professional means "at this company", not merely "not gmail".
    """
    domain = email.rsplit("@", 1)[-1].lower()
    if domain in _PUBLIC_EMAIL_DOMAINS:
        return False
    if company_domain is None:
        return False
    return domain == company_domain.lower()


def find_phones(text: str) -> list[str]:
    """Return phone-like candidates, normalized to digits-with-leading-plus.

    This is a heuristic, not a validator: it reports what looks like a phone
    number so a human/downstream stage can judge it, never a claim that the
    number is real or reachable.
    """
    seen: list[str] = []
    for match in _PHONE_RE.finditer(text):
        raw = match.group(1)
        digits = re.sub(r"[^\d+]", "", raw)
        digit_count = len(re.sub(r"\D", "", digits))
        if digit_count < 7 or digit_count > 15:
            continue
        if digits not in seen:
            seen.append(digits)
    return seen


def normalize_domain(value: str) -> str | None:
    """Normalize a bare domain or a URL down to its lowercase host, no
    'www.', no port. Returns None for empty/unparseable input."""
    if not value:
        return None
    candidate = value.strip()
    if "://" not in candidate:
        candidate = f"http://{candidate}"
    host = urlsplit(candidate).hostname
    if not host:
        return None
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def normalize_company_name(name: str) -> str:
    """Collapse whitespace and strip a trailing legal suffix for display.
    The result is still a display name, not a dedup key — use
    `company_dedup_key` for matching."""
    cleaned = " ".join(name.split()).strip(" -|")
    lowered = cleaned.lower()
    for suffix in _LEGAL_SUFFIXES:
        if lowered.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip(" ,.")
            break
    return cleaned


def company_dedup_key(domain: str | None, name: str) -> str:
    """Stable per-tenant dedup key: prefer domain (a fact from the fetch
    URL), fall back to a normalized name only when no domain is known."""
    if domain:
        return f"domain:{normalize_domain(domain) or domain.lower()}"
    return f"name:{normalize_company_name(name).lower()}"


def normalize_person_name(name: str) -> str:
    cleaned = " ".join(name.split()).strip(" ,.")
    return unicodedata.normalize("NFC", cleaned)


def normalize_job_title(title: str) -> str:
    return " ".join(title.split()).strip(" ,.-")


def find_job_title_near(text: str) -> str | None:
    """Best-effort: return the first known title keyword found verbatim in
    `text` (e.g. the line/segment surrounding a contact's name), title-cased
    for display. Returns None rather than guess when nothing matches —
    fabricating a title is worse than leaving it blank."""
    lowered = text.lower()
    for keyword in _JOB_TITLE_KEYWORDS:
        idx = lowered.find(keyword)
        if idx != -1:
            return normalize_job_title(text[idx : idx + len(keyword)]).title()
    return None
