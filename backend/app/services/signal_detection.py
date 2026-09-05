"""Signal Intelligence (C4): Evidence -> Signal.

    Evidence
       v
    detect_signal_type() — deterministic, keyword-based, explainable
       v
    Signal (fingerprint-deduped, same mechanism the manual API already uses)

A Signal is preuve + interprétation contrôlée: it never exists without a
supporting Evidence, and the reason it was detected (which evidence_type
prior, which keywords matched) is always recoverable — nothing here is a
black box. Reuses the existing SIGNAL_TYPES taxonomy (app.models.signal) and
the existing fingerprint mechanism (moved here from the manual API so both
code paths dedupe identically, not with a parallel scheme).
"""

from __future__ import annotations

import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.metrics import metrics
from app.models.evidence import Evidence
from app.models.signal import Signal

# Evidence.evidence_type values that, on their own (already page-classified
# during C3 via a real URL/title signal), are sufficient support for a
# same-named Signal — no further keyword confirmation required.
_DIRECT_EVIDENCE_TO_SIGNAL = {
    "hiring": "hiring",
    "funding": "funding",
    "partnership": "partnership",
    "acquisition": "acquisition",
    "certification": "certification",
    "expansion": "expansion",
}

# Evidence.evidence_type values that are suggestive but NOT sufficient alone
# (e.g. a "leadership" page is often just a static team bio page, not a
# change event) — require a keyword match in the text before promoting to a
# signal, and only ever to this one specific signal_type.
_SUGGESTIVE_EVIDENCE_TO_SIGNAL = {
    "leadership": "leadership_change",
    "product": "product_launch",
    "technology": "migration",
}

# Keyword sets per signal_type, used both to confirm a suggestive prior and
# to classify evidence with no usable prior at all (company_profile/website/
# news/press/job_posting/social_business/other). Lowercase, checked as
# substrings of the lowercased evidence text.
SIGNAL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "hiring": (
        "we're hiring",
        "we are hiring",
        "now hiring",
        "join our team",
        "open positions",
        "open position",
        "career opportunities",
        "we're growing our team",
    ),
    "expansion": (
        "expanding",
        "expansion",
        "new office",
        "new location",
        "opening a new",
        "growing our team",
        "scaling our",
    ),
    "funding": (
        "raised",
        "funding round",
        "series a",
        "series b",
        "series c",
        "series d",
        "seed round",
        "venture capital",
        "closed a round",
        "secures funding",
        "million in funding",
    ),
    "product_launch": (
        "launch",
        "launching",
        "unveil",
        "introduces",
        "announcing",
        "new product",
        "now available",
        "we're excited to introduce",
    ),
    "partnership": (
        "partnership",
        "partners with",
        "collaborat",
        "teams up",
        "strategic alliance",
        "joint venture",
    ),
    "leadership_change": (
        "appoints",
        "appointed",
        "new ceo",
        "new cto",
        "new cfo",
        "new coo",
        "steps down",
        "joins as",
        "welcomes",
        "promoted to",
        "named as",
    ),
    "migration": (
        "migrated to",
        "migration to",
        "moved to the cloud",
        "adopts",
        "switches to",
        "migrating from",
    ),
    "certification": (
        "certified",
        "certification",
        "iso 27001",
        "soc 2",
        "compliance achieved",
    ),
    "acquisition": (
        "acquires",
        "acquired",
        "acquisition of",
        "merger",
        "acquired by",
        "to be acquired",
    ),
}

# Fixed priority order for the broad scan (no prior): first category with a
# keyword hit wins, so results are deterministic even with overlapping words.
_BROAD_SCAN_ORDER = (
    "funding",
    "acquisition",
    "leadership_change",
    "product_launch",
    "partnership",
    "hiring",
    "expansion",
    "certification",
    "migration",
)


def _matched_keywords(text: str, signal_type: str) -> list[str]:
    lowered = text.lower()
    return [kw for kw in SIGNAL_KEYWORDS.get(signal_type, ()) if kw in lowered]


def detect_signal_type(
    text: str, evidence_type: str | None
) -> tuple[str, float, list[str]] | None:
    """Pure classification: given evidence text and its evidence_type prior,
    return (signal_type, confidence, matched_keywords) or None when there is
    no support for any signal at all.

    confidence here is the signal's own base confidence, deterministic and
    documented — NOT a scoring formula. `ingest_evidence` combines it with
    the source Evidence's own confidence, so a shaky Evidence can never
    produce an artificially strong Signal.
    """
    if evidence_type in _DIRECT_EVIDENCE_TO_SIGNAL:
        signal_type = _DIRECT_EVIDENCE_TO_SIGNAL[evidence_type]
        return signal_type, 0.85, _matched_keywords(text, signal_type)

    if evidence_type in _SUGGESTIVE_EVIDENCE_TO_SIGNAL:
        signal_type = _SUGGESTIVE_EVIDENCE_TO_SIGNAL[evidence_type]
        matched = _matched_keywords(text, signal_type)
        if matched:
            return signal_type, 0.75, matched
        return None  # a static leadership/product page alone is not an event

    for signal_type in _BROAD_SCAN_ORDER:
        matched = _matched_keywords(text, signal_type)
        if matched:
            return signal_type, 0.6, matched

    return None


def signal_fingerprint(
    tenant_id: uuid.UUID,
    *,
    signal_type: str,
    company_id: uuid.UUID,
    source_url: str | None,
    source_name: str | None,
) -> str:
    """The single fingerprint scheme for signal dedup, shared by the manual
    creation API and the automated detector below. Do not fork this."""
    raw = json.dumps(
        {
            "tenant_id": str(tenant_id),
            "signal_type": signal_type,
            "company_id": str(company_id),
            "source_url": (source_url or "").strip(),
            "source_name": (source_name or "").strip(),
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def ingest_evidence(
    db: AsyncSession, tenant_id: uuid.UUID, evidence: Evidence
) -> Signal | None:
    """Detect and persist a Signal from one piece of Evidence.

    Returns None when there is no support for any signal (nothing is ever
    fabricated). Returns the EXISTING signal, unchanged, on a fingerprint
    collision (idempotent — unlike the manual POST /signals endpoint, which
    409s on a duplicate since a human re-submitting the same signal is
    likely a mistake; an automated detector re-run against the same
    evidence is the expected, normal case). A Signal is never created
    without a company to attach it to.
    """
    if evidence.company_id is None:
        return None

    text = f"{evidence.title or ''} {evidence.excerpt or ''}"
    detection = detect_signal_type(text, evidence.evidence_type)
    if detection is None:
        return None
    signal_type, base_confidence, matched = detection

    confidence = round(min(evidence.confidence, base_confidence), 4)
    fp = signal_fingerprint(
        tenant_id,
        signal_type=signal_type,
        company_id=evidence.company_id,
        source_url=evidence.source_url,
        source_name=evidence.source_name,
    )
    existing = await db.execute(
        select(Signal).where(
            Signal.tenant_id == tenant_id,
            Signal.fingerprint == fp,
            Signal.deleted_at.is_(None),
        )
    )
    dup = existing.scalar_one_or_none()
    if dup is not None:
        return dup

    label = signal_type.replace("_", " ").title()
    description = (
        f"Detected from evidence_type={evidence.evidence_type!r}; "
        f"matched keywords: {matched or '(evidence_type prior only)'}"
    )
    signal = Signal(
        tenant_id=tenant_id,
        company_id=evidence.company_id,
        evidence_id=evidence.id,
        signal_type=signal_type,
        title=f"{label} signal detected",
        description=description,
        source_url=evidence.source_url,
        source_name=evidence.source_name,
        detected_at=evidence.published_at or evidence.collected_at,
        confidence=confidence,
        status="new",
        fingerprint=fp,
    )
    db.add(signal)
    await db.flush()
    await db.refresh(signal)
    metrics.inc("signals_detected_total")
    return signal
