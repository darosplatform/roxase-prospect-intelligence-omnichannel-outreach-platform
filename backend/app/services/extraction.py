"""Extraction & Normalization (C3).

    RawDocument
         v
    ExtractedPage (HTML/text parsed, page classified, candidates found)
         v
    Company / Contact (get-or-create, tenant-scoped dedup)
         v
    one Evidence record per page, provenance kept in evidence_metadata

Boundary: C3 may create Company, Contact and Evidence. It NEVER creates
Signal, Lead or Score — those are C4/C5. It never fabricates a field: a
company name only comes from a real <title>/og:site_name on the page, a
contact's name is only set when literally present as text (never derived
from an email's local part), and a job title is only set when a known title
keyword appears verbatim near the contact.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.extraction_utils import (
    classify_page,
    find_emails,
    find_job_title_near,
    find_phones,
    is_professional_email,
    normalize_company_name,
    normalize_domain,
)
from app.models.company import Company
from app.models.contact import Contact
from app.models.discovery import DiscoverySource, RawDocument
from app.models.evidence import Evidence

EXTRACTABLE_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml", "text/plain"})

# Evidence.evidence_type is a fixed enum (app.models.evidence.EVIDENCE_TYPES);
# every page_type must map to a member of it. "website" is the catch-all.
_PAGE_TYPE_TO_EVIDENCE_TYPE = {
    "about": "company_profile",
    "contact": "company_profile",
    "team": "leadership",
    "leadership": "leadership",
    "careers": "hiring",
    "products": "product",
    "news": "news",
    "press": "news",
    "partnerships": "partnership",
    "other": "website",
}

EXCERPT_MAX_CHARS = 600


@dataclass
class ExtractedPage:
    url: str
    page_type: str
    title: str | None
    text: str
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    og_site_name: str | None = None


@dataclass
class ExtractionOutcome:
    company_id: uuid.UUID | None
    contact_ids: list[uuid.UUID]
    evidence_id: uuid.UUID | None
    page_type: str
    skipped_reason: str | None = None


def extract_page(fetch_url: str, content_type: str | None, body: str) -> ExtractedPage | None:
    """Parse a fetched body into structured candidates.

    Returns None when the content type isn't one C3 knows how to read yet —
    never guesses at binary or unrecognized formats.
    """
    base_ct = (content_type or "").split(";", 1)[0].strip().lower()
    if base_ct not in EXTRACTABLE_CONTENT_TYPES:
        return None

    if base_ct == "text/plain":
        text = body
        title = None
        og_site_name = None
    else:
        soup = BeautifulSoup(body, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else None
        og_tag = soup.find("meta", attrs={"property": "og:site_name"})
        og_content = og_tag.get("content") if og_tag else None
        og_site_name = og_content.strip() if og_content else None
        text = soup.get_text(separator=" ", strip=True)
        # mailto:/tel: links are a stronger signal than scanning body text.
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.lower().startswith("mailto:"):
                text += " " + href.split(":", 1)[1].split("?", 1)[0]
            elif href.lower().startswith("tel:"):
                text += " " + href.split(":", 1)[1]

    page_type = classify_page(fetch_url, title)
    return ExtractedPage(
        url=fetch_url,
        page_type=page_type,
        title=title,
        text=text,
        emails=find_emails(text),
        phones=find_phones(text),
        og_site_name=og_site_name,
    )


async def _find_company_by_domain(
    db: AsyncSession, tenant_id: uuid.UUID, domain: str | None
) -> Company | None:
    if not domain:
        return None
    result = await db.execute(
        select(Company).where(Company.tenant_id == tenant_id, Company.domain == domain)
    )
    return result.scalar_one_or_none()


async def _get_or_create_company(
    db: AsyncSession, tenant_id: uuid.UUID, *, domain: str | None, name: str | None
) -> Company:
    existing = await _find_company_by_domain(db, tenant_id, domain)
    if existing is not None:
        return existing
    company = Company(
        tenant_id=tenant_id,
        legal_name=name or domain or "Unknown",
        domain=domain,
        source="discovery",
    )
    db.add(company)
    await db.flush()
    await db.refresh(company)
    return company


async def _find_contact_by_email(
    db: AsyncSession, tenant_id: uuid.UUID, email: str
) -> Contact | None:
    result = await db.execute(
        select(Contact).where(Contact.tenant_id == tenant_id, Contact.email == email)
    )
    return result.scalar_one_or_none()


async def _get_or_create_contact(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    company_id: uuid.UUID | None,
    email: str,
    job_title: str | None,
) -> Contact:
    existing = await _find_contact_by_email(db, tenant_id, email)
    if existing is not None:
        # Enrich, never overwrite an already-known value with a guess.
        if job_title and not existing.job_title:
            existing.job_title = job_title
        if company_id and not existing.company_id:
            existing.company_id = company_id
        await db.flush()
        return existing
    contact = Contact(
        tenant_id=tenant_id,
        company_id=company_id,
        email=email,
        job_title=job_title,
        source="discovery",
    )
    db.add(contact)
    await db.flush()
    await db.refresh(contact)
    return contact


async def ingest_raw_document(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    raw_document: RawDocument,
    source: DiscoverySource,
) -> ExtractionOutcome:
    """Turn one already-fetched RawDocument into Company/Contact candidates
    plus one provenance-preserving Evidence record. Idempotent per tenant:
    re-running against the same page finds and enriches the same rows
    instead of duplicating them.
    """
    page = extract_page(
        raw_document.fetch_url, raw_document.content_type, raw_document.content_body or ""
    )
    if page is None:
        return ExtractionOutcome(
            company_id=None,
            contact_ids=[],
            evidence_id=None,
            page_type="unsupported",
            skipped_reason="unsupported_content_type",
        )

    domain = normalize_domain(raw_document.fetch_url)
    display_name = page.og_site_name or page.title
    company_name = normalize_company_name(display_name) if display_name else None
    company = await _get_or_create_company(db, tenant_id, domain=domain, name=company_name)

    contact_ids: list[uuid.UUID] = []
    for raw_email in page.emails:
        email = raw_email.lower()
        professional = is_professional_email(email, domain)
        job_title = find_job_title_near(page.text) if professional else None
        contact = await _get_or_create_contact(
            db,
            tenant_id,
            company_id=company.id,
            email=email,
            job_title=job_title,
        )
        contact_ids.append(contact.id)

    evidence_type = _PAGE_TYPE_TO_EVIDENCE_TYPE.get(page.page_type, "website")
    excerpt = page.text[:EXCERPT_MAX_CHARS] or None
    evidence = Evidence(
        tenant_id=tenant_id,
        company_id=company.id,
        source_url=raw_document.fetch_url,
        source_name=domain,
        evidence_type=evidence_type,
        title=page.title,
        excerpt=excerpt,
        content_hash=raw_document.content_hash,
        collected_at=raw_document.fetched_at,
        # Deterministic, documented, not a scoring formula: a clean
        # structured signal (og:site_name) earns a higher confidence than a
        # bare heuristic scrape of visible text.
        confidence=0.9 if page.og_site_name else 0.7,
        evidence_metadata={
            "raw_document_id": str(raw_document.id),
            "discovery_source_id": str(source.id),
            "discovery_job_id": str(source.job_id),
            "page_type": page.page_type,
            "emails_found": len(page.emails),
            "phones_found": len(page.phones),
        },
    )
    db.add(evidence)
    await db.flush()
    await db.refresh(evidence)

    return ExtractionOutcome(
        company_id=company.id,
        contact_ids=contact_ids,
        evidence_id=evidence.id,
        page_type=page.page_type,
    )
