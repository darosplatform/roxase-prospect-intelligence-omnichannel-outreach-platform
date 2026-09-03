"""Deterministic, explainable lead scoring engine for ROXASE.

Pipeline enforced here:

    Source -> Evidence -> Signal -> Qualification -> Lead Score -> Priority

Design rules (from the chantier requirements):
  * No AI / no randomisation: the same dataset + the same scoring version
    always yields the same score.
  * The score is a weighted sum of five independent dimensions tracked as
    separate metrics so that a weak signal can never be turned into a strong
    truth on its own.
  * Every contributing factor is returned with the evidence ids that produced
    it, so a score is always explainable as far back as the source_url.
  * Dismissed signals are excluded. Low signal confidence and old data only
    attenuate their influence.
  * All weights are centralized here, never scattered across endpoints.
  * Dimensions are kept separate from `lead.score`: a high lead_score is only
    produced when the underlying evidence supports it.

All functions are pure and testable; the DB is only read by the router before
calling `assess_lead`.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evidence import Evidence
from app.models.lead import Lead
from app.models.signal import SIGNAL_TYPES, Signal

# ---------------------------------------------------------------------------
# Centralized, versioned configuration
# ---------------------------------------------------------------------------

SCORING_VERSION = "v1"

# Per-signal-type contribution to `signal_score` (0..1 each).
SIGNAL_BASE_WEIGHT: dict[str, float] = {
    "hiring": 0.6,
    "expansion": 0.6,
    "funding": 0.7,
    "product_launch": 0.7,
    "partnership": 0.5,
    "leadership_change": 0.4,
    "migration": 0.6,
    "certification": 0.4,
    "acquisition": 0.8,
    "other": 0.3,
}

# Signal types that indicate buying intent.
INTENT_SIGNAL_TYPES = {
    "hiring",
    "funding",
    "expansion",
    "product_launch",
    "migration",
    "acquisition",
}

# Signal types that indicate org expansion / strategic fit.
FIT_SIGNAL_TYPES = {
    "hiring",
    "expansion",
    "funding",
    "acquisition",
}

# Final dimension weights. Must sum to 1.0.
DIMENSION_WEIGHTS: dict[str, float] = {
    "fit": 0.25,
    "intent": 0.30,
    "signal": 0.20,
    "data_confidence": 0.15,
    "freshness": 0.10,
}

# Freshness thresholds (days) for the most recent active signal.
FRESHNESS_THRESHOLDS_DAYS: list[tuple[int, float]] = [
    (30, 1.0),
    (90, 0.7),
    (180, 0.4),
    (365, 0.2),
]

# Neutral data confidence when no evidence has been collected.
NO_EVIDENCE_DATA_CONFIDENCE = 40.0

assert sum(DIMENSION_WEIGHTS.values()) == 1.0, "dimension weights must sum to 1.0"
for _type in SIGNAL_TYPES:
    assert _type in SIGNAL_BASE_WEIGHT, f"missing signal weight for {_type}"


# ---------------------------------------------------------------------------
# Public result types
# ---------------------------------------------------------------------------


@dataclass
class ScoreFactor:
    name: str
    impact: float
    evidence_ids: list[uuid.UUID] = field(default_factory=list)


@dataclass
class ScoreResult:
    score: int
    version: str
    fit: float
    intent: float
    signal: float
    data_confidence: float
    freshness: float
    factors: list[ScoreFactor]
    computed_at: datetime

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "scoring_version": self.version,
            "breakdown": {
                "fit": round(self.fit, 2),
                "intent": round(self.intent, 2),
                "signal": round(self.signal, 2),
                "data_confidence": round(self.data_confidence, 2),
                "freshness": round(self.freshness, 2),
            },
            "factors": [
                {
                    "name": f.name,
                    "impact": round(f.impact, 2),
                    "evidence_ids": [str(e) for e in f.evidence_ids],
                }
                for f in self.factors
            ],
            "computed_at": self.computed_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Scoring primitives
# ---------------------------------------------------------------------------


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _freshness_score(days: float | None) -> float:
    """Recency score in [0, 100] based on the age of the newest active signal."""
    if days is None:
        return 0.0
    for threshold_days, score in FRESHNESS_THRESHOLDS_DAYS:
        if days <= threshold_days:
            return score * 100
    return 10.0


def _age_days(now: datetime, when: datetime) -> float:
    return max(0.0, (now - when).total_seconds() / 86400.0)


def _signal_contributions(active_signals: list[Signal]) -> dict[str, float]:
    """Aggregate per-type contribution from non-dismissed, non-deleted signals.

    Each signal contributes `base_weight[type] * confidence` so low-confidence
    signals carry proportionally less weight.
    """
    result: dict[str, float] = {}
    for signal in active_signals:
        base = SIGNAL_BASE_WEIGHT.get(signal.signal_type, SIGNAL_BASE_WEIGHT["other"])
        result[signal.signal_type] = result.get(signal.signal_type, 0.0) + (
            base * signal.confidence
        )
    return result


def _dimension_from_contributions(contributions: dict[str, float]) -> int:
    return round(_clamp(100.0 * min(1.0, sum(contributions.values()))))


def _evidence_ids_for_signals(signals: list[Signal]) -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []
    for signal in signals:
        if signal.evidence_id is not None:
            ids.append(signal.evidence_id)
    return ids


def _signal_factors(
    active_signals: list[Signal], dimension: str, types: set[str]
) -> list[ScoreFactor]:
    """Build one factor per distinct signal type that drove a dimension."""
    contributors = [s for s in active_signals if s.signal_type in types]
    factors: list[ScoreFactor] = []
    for signal_type in sorted({s.signal_type for s in contributors}):
        matching = [s for s in contributors if s.signal_type == signal_type]
        impact = sum(SIGNAL_BASE_WEIGHT[s.signal_type] * s.confidence for s in matching)
        factors.append(
            ScoreFactor(
                name=f"{dimension}:{signal_type}",
                impact=round(_clamp(impact * 100.0), 2),
                evidence_ids=_evidence_ids_for_signals(matching),
            )
        )
    return factors


def _data_confidence_score(
    active_signals: list[Signal], evidence_lookup: dict[uuid.UUID, Evidence]
) -> float:
    """Blend evidence reliability into a data-confidence score.

    A lead with no evidence scores a low, non-zero floor so we never claim
    strength without proof.
    """
    evidence_items = [_evidence_lookup(evidence_lookup, s) for s in active_signals]
    evidence_items = [e for e in evidence_items if e is not None]
    if not evidence_items:
        return NO_EVIDENCE_DATA_CONFIDENCE
    avg_confidence = sum(e.confidence for e in evidence_items) / len(evidence_items)
    return _clamp(avg_confidence * 100.0)


def _evidence_lookup(
    evidence_lookup: dict[uuid.UUID, Evidence], signal: Signal
) -> Evidence | None:
    if signal.evidence_id is None:
        return None
    return evidence_lookup.get(signal.evidence_id)


def _fit_score(active_signals: list[Signal]) -> int:
    """Org/segment fit derived from expansion-oriented signals."""
    contributions = {
        signal.signal_type: SIGNAL_BASE_WEIGHT[signal.signal_type] * signal.confidence
        for signal in active_signals
        if signal.signal_type in FIT_SIGNAL_TYPES
    }
    if not contributions:
        # Neutral baseline; never rewards absence of evidence.
        return 50
    return _dimension_from_contributions(contributions)


# ---------------------------------------------------------------------------
# Public engine entry points
# ---------------------------------------------------------------------------


def compute_score(
    active_signals: list[Signal],
    evidence_items: list[Evidence],
    now: datetime | None = None,
) -> ScoreResult:
    """Compute the complete, explainable score for a set of active signals.

    Pure and deterministic: identical inputs (optionally pinned to a fixed
    ``now``) produce identical output for a given ``SCORING_VERSION``.

    Dismissed signals never contribute — they are excluded here so the
    invariant holds regardless of how this engine is invoked.
    """
    now = now or datetime.now(UTC)
    active_signals = [s for s in active_signals if s.status != "dismissed"]
    evidence_lookup = {e.id: e for e in evidence_items}

    if not active_signals:
        return ScoreResult(
            score=0,
            version=SCORING_VERSION,
            fit=50.0,
            intent=0.0,
            signal=0.0,
            data_confidence=NO_EVIDENCE_DATA_CONFIDENCE,
            freshness=0.0,
            factors=[],
            computed_at=now,
        )

    contributions = _signal_contributions(active_signals)
    signal_score = _dimension_from_contributions(contributions)

    intent_contributions = {
        k: v for k, v in contributions.items() if k in INTENT_SIGNAL_TYPES
    }
    intent_score = (
        _dimension_from_contributions(intent_contributions)
        if intent_contributions
        else 0
    )

    fit_score = _fit_score(active_signals)
    data_confidence = _data_confidence_score(active_signals, evidence_lookup)

    newest = min(active_signals, key=lambda s: s.detected_at)
    freshness = _freshness_score(_age_days(now, newest.detected_at))

    lead_score = round(
        DIMENSION_WEIGHTS["fit"] * fit_score
        + DIMENSION_WEIGHTS["intent"] * intent_score
        + DIMENSION_WEIGHTS["signal"] * signal_score
        + DIMENSION_WEIGHTS["data_confidence"] * data_confidence
        + DIMENSION_WEIGHTS["freshness"] * freshness
    )
    lead_score = _clamp(lead_score, 0, 100)

    factors: list[ScoreFactor] = []
    factors.extend(_signal_factors(active_signals, "intent", INTENT_SIGNAL_TYPES))
    factors.extend(_signal_factors(active_signals, "fit", FIT_SIGNAL_TYPES))
    if not evidence_lookup:
        factors.append(
            ScoreFactor(name="data_confidence:no_evidence", impact=NO_EVIDENCE_DATA_CONFIDENCE)
        )

    return ScoreResult(
        score=int(lead_score),
        version=SCORING_VERSION,
        fit=float(fit_score),
        intent=float(intent_score),
        signal=float(signal_score),
        data_confidence=float(data_confidence),
        freshness=float(freshness),
        factors=factors,
        computed_at=now,
    )


async def assess_lead(db: AsyncSession, lead: Lead) -> ScoreResult:
    """Load the tenant-scoped signals + evidence for a lead and score it.

    Only signals belonging to the lead's tenant and not dismissed/deleted are
    considered, so a foreign tenant can never influence the score.
    """
    stmt = select(Signal).where(
        Signal.tenant_id == lead.tenant_id,
        Signal.deleted_at.is_(None),
        Signal.status != "dismissed",  # dismissed signals never contribute
    )
    if lead.company_id is not None:
        stmt = stmt.where(Signal.company_id == lead.company_id)
    result = await db.execute(stmt)
    active: list[Signal] = list(result.scalars().all())

    evidence_ids = {s.evidence_id for s in active if s.evidence_id is not None}
    evidence_items: list[Evidence] = []
    if evidence_ids:
        ev_result = await db.execute(
            select(Evidence).where(
                Evidence.id.in_(evidence_ids),
                Evidence.tenant_id == lead.tenant_id,
            )
        )
        evidence_items = list(ev_result.scalars().all())

    return compute_score(active, evidence_items)


def fingerprint_of(payload_for_hash: dict) -> str:
    """Stable fingerprint used to avoid duplicate scoring / evidence."""
    raw = json.dumps(payload_for_hash, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()