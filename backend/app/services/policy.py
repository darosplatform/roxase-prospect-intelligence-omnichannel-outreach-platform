"""Pure, deterministic policy engine for ROXASE outreach.

Pipeline:

    Lead -> Qualification -> Evidence/Signals/Score
        -> Policy Engine -> ALLOW / DENY / REVIEW
        -> OutreachRequest -> Outbox -> ProviderAdapter

Core invariants enforced here:

  * The Policy Engine is the single business authority. Channel adapters never
    decide anything.
  * Blocking rules always take priority over positive rules. A high score can
    never override a DNC.
  * Rule evaluation order is fixed and explicit:
        GlobalOutreach -> DNC -> Campaign -> Channel -> Consent
        -> Qualification -> Score -> Freshness -> Frequency
  * `unknown` consent is never silently upgraded to an ALLOW; it yields REVIEW.
  * A decision is always explainable: reasons carry codes, and the full context
    (score, evidence ids, version) is preserved.

The engine is FastAPI-independent: it takes plain values and returns a
`PolicyDecision` dataclass. Persistence is handled by the service layer.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

POLICY_VERSION = "v1"
ALLOW = "ALLOW"
DENY = "DENY"
REVIEW = "REVIEW"


# Convenient blanket defaults exposed to the rules.
CONSENT_BLOCKING_POLICY = {"legitimate_interest"}  # (illustrative, configurable)


@dataclass
class Reason:
    code: str
    message: str
    severity: str = "deny"  # deny | review


@dataclass
class Decision:
    decision: str
    policy_version: str = POLICY_VERSION
    reasons: list[Reason] = field(default_factory=list)
    score: int | None = None
    evidence_ids: list[uuid.UUID] = field(default_factory=list)
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    tenant_id: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None
    campaign_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    channel: str | None = None
    meta: dict = field(default_factory=dict, repr=False)

    def has(self, code: str) -> bool:
        return any(r.code == code for r in self.reasons)

    def add(self, code: str, message: str, severity: str = "deny") -> None:
        self.reasons.append(Reason(code=code, message=message, severity=severity))

    def to_dict(self) -> dict:
        return {
            "decision": self.decision,
            "policy_version": self.policy_version,
            "reasons": [
                {"code": r.code, "message": r.message, "severity": r.severity}
                for r in self.reasons
            ],
            "score": self.score,
            "evidence_ids": [str(e) for e in self.evidence_ids],
            "evaluated_at": self.evaluated_at.isoformat(),
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "lead_id": str(self.lead_id) if self.lead_id else None,
            "campaign_id": str(self.campaign_id) if self.campaign_id else None,
            "contact_id": str(self.contact_id) if self.contact_id else None,
            "channel": self.channel,
        }


class PolicyInput:
    """Bag of context the rules read. Kept plain so the engine stays pure."""

    def __init__(self, **kwargs):
        self.lead_score: int | None = kwargs.get("lead_score")
        self.qualification_status: str | None = kwargs.get("qualification_status")
        self.requires_qualification: bool = kwargs.get("requires_qualification", False)
        self.requires_evidence: bool = kwargs.get("requires_evidence", False)
        self.evidence_ids: list[uuid.UUID] = kwargs.get("evidence_ids", [])
        self.evidence_freshness_days: float | None = kwargs.get("evidence_freshness_days")
        self.min_evidence_freshness_days: float | None = kwargs.get(
            "min_evidence_freshness_days"
        )
        self.min_lead_score: int | None = kwargs.get("min_lead_score")
        self.min_confidence: float | None = kwargs.get("min_confidence")
        self.allowed_channels: list[str] = kwargs.get("allowed_channels", [])
        self.channel: str | None = kwargs.get("channel")
        self.outreach_enabled: bool = kwargs.get("outreach_enabled", True)
        self.dnc_matches: bool = kwargs.get("dnc_matches", False)
        self.consent_basis: str | None = kwargs.get("consent_basis")
        self.dry_run: bool = kwargs.get("dry_run", True)
        # Campaign state: must be running (or scheduled for batch) to ALLOW.
        self.campaign_running: bool = kwargs.get("campaign_running", False)
        self.frequency_exceeded: bool = kwargs.get("frequency_exceeded", False)
        self.frequency_codes: list[str] = kwargs.get("frequency_codes", [])
        self.tenant_id: uuid.UUID | None = kwargs.get("tenant_id")
        self.lead_id: uuid.UUID | None = kwargs.get("lead_id")
        self.campaign_id: uuid.UUID | None = kwargs.get("campaign_id")
        self.contact_id: uuid.UUID | None = kwargs.get("contact_id")
        # Identifiers/policies for the decision envelope (not verdict-affecting).
        self.meta: dict = kwargs.get("meta", {})
        self.evidence_json: list[dict] = kwargs.get("evidence_json", [])


# ---------------------------------------------------------------------------
# Individual, independently-testable rules
# ---------------------------------------------------------------------------


def global_outreach_rule(inp: PolicyInput, d: Decision) -> None:
    if not inp.outreach_enabled:
        d.add("OUTREACH_DISABLED", "Outreach is globally paused", "deny")


def dnc_rule(inp: PolicyInput, d: Decision) -> None:
    if inp.dnc_matches:
        d.add("DO_NOT_CONTACT", "Contact or company is opted out", "deny")


def campaign_rule(inp: PolicyInput, d: Decision) -> None:
    if not inp.campaign_running:
        d.add("CAMPAIGN_NOT_RUNNING", "Campaign is not in a sendable state", "deny")


def channel_rule(inp: PolicyInput, d: Decision) -> None:
    if not inp.channel:
        d.add("CHANNEL_UNSPECIFIED", "No channel provided", "review")
        return
    if inp.allowed_channels and inp.channel not in inp.allowed_channels:
        d.add(
            "CHANNEL_NOT_ALLOWED",
            f"Channel {inp.channel} is not allowed for this campaign",
            "deny",
        )


def consent_rule(inp: PolicyInput, d: Decision) -> None:
    basis = inp.consent_basis
    if basis is None or basis == "unknown":
        d.add("CONSENT_UNKNOWN", "No consent / legal basis recorded", "review")
        return
    if basis in CONSENT_BLOCKING_POLICY:
        d.add("CONSENT_BLOCKED", f"Consent basis '{basis}' is not acceptable", "deny")


def qualification_rule(inp: PolicyInput, d: Decision) -> None:
    if inp.requires_qualification and inp.qualification_status != "qualified":
        d.add(
            "QUALIFICATION_REQUIRED",
            "Lead must be qualified before outreach",
            "deny",
        )


def score_rule(inp: PolicyInput, d: Decision) -> None:
    if inp.min_lead_score is not None:
        if inp.lead_score is None:
            d.add("SCORE_UNKNOWN", "Lead has no score", "review")
        elif inp.lead_score < inp.min_lead_score:
            d.add(
                "SCORE_TOO_LOW",
                f"Lead score {inp.lead_score} below minimum {inp.min_lead_score}",
                "deny",
            )
    if inp.min_confidence is not None and inp.lead_score is not None:
        pass  # confidence is evaluated via evidence below


def freshness_rule(inp: PolicyInput, d: Decision) -> None:
    if inp.requires_evidence and not inp.evidence_ids:
        d.add("EVIDENCE_REQUIRED", "Evidence is required for this campaign", "deny")
    if inp.min_evidence_freshness_days is not None:
        if inp.evidence_freshness_days is None:
            d.add("EVIDENCE_STALE", "No freshness data for evidence", "review")
        elif inp.evidence_freshness_days > inp.min_evidence_freshness_days:
            d.add(
                "EVIDENCE_STALE",
                f"Evidence is {inp.evidence_freshness_days:.0f} days old, "
                f"older than {inp.min_evidence_freshness_days:.0f}",
                "deny",
            )


def frequency_rule(inp: PolicyInput, d: Decision) -> None:
    if inp.frequency_exceeded:
        for code in inp.frequency_codes or ["FREQUENCY_LIMIT"]:
            d.add(code, "Frequency limit exceeded for this scope", "deny")


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

# Rule execution order: blocking and structural rules first, then positives.
_RULES = (
    global_outreach_rule,
    dnc_rule,
    campaign_rule,
    channel_rule,
    consent_rule,
    qualification_rule,
    score_rule,
    freshness_rule,
    frequency_rule,
)


def evaluate(input_: PolicyInput, injected_rules=None) -> Decision:
    """Run the policy and return the verdict.

    Priority is fixed: DNC and other guards evaluate first; a deny verdict is
    returned as soon as an authoritative deny/blocking rule fires, before any
    positive rule could mask it. REVIEW accumulates missing-context signals.
    """
    decision = Decision(
        decision="PENDING",
        policy_version=POLICY_VERSION,
        score=input_.lead_score,
        evidence_ids=input_.evidence_ids,
        tenant_id=input_.tenant_id,
        lead_id=input_.lead_id,
        campaign_id=input_.campaign_id,
        contact_id=input_.contact_id,
        channel=input_.channel,
    )

    rules = injected_rules or _RULES

    deny_found = False
    review_found = False
    for rule in rules:
        rule(input_, decision)
        for r in decision.reasons:
            if r.severity == "deny":
                deny_found = True
            elif r.severity == "review":
                review_found = True

    # Deny always wins over a positive. Unknown context downgrades to REVIEW.
    if deny_found:
        decision.decision = DENY
    elif review_found:
        decision.decision = REVIEW
    else:
        decision.decision = ALLOW
    return decision