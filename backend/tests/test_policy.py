import uuid

from app.services.policy import (
    ALLOW,
    DENY,
    REVIEW,
    PolicyInput,
    evaluate,
)

TENANT = uuid.uuid4()


def _input(**overrides):
    base = dict(
        tenant_id=TENANT,
        lead_id=uuid.uuid4(),
        lead_score=90,
        qualification_status="qualified",
        requires_qualification=False,
        requires_evidence=False,
        evidence_ids=[],
        evidence_freshness_days=1.0,
        min_evidence_freshness_days=None,
        min_lead_score=None,
        min_confidence=None,
        allowed_channels=["email", "whatsapp"],
        channel="email",
        outreach_enabled=True,
        dnc_matches=False,
        consent_basis="consent",
        dry_run=True,
        campaign_running=True,
        frequency_exceeded=False,
        frequency_codes=[],
    )
    base.update(overrides)
    return PolicyInput(**base)


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------


def test_allows_when_nothing_blocks():
    d = evaluate(_input())
    assert d.decision == ALLOW
    assert d.policy_version == "v1"


# ---------------------------------------------------------------------------
# Ordering & priority: blocking rules beat positive rules
# ---------------------------------------------------------------------------


def test_dnc_beats_high_score():
    d = evaluate(_input(dnc_matches=True, lead_score=100, consent_basis="consent"))
    assert d.decision == DENY
    assert d.has("DO_NOT_CONTACT")


def test_outreach_kill_switch_denies():
    d = evaluate(_input(outreach_enabled=False))
    assert d.decision == DENY
    assert d.has("OUTREACH_DISABLED")


def test_dnc_evaluated_before_score_and_blocks_review():
    # even a REVIEW-inducing condition cannot upgrade a DNC deny
    d = evaluate(_input(dnc_matches=True, consent_basis=None))
    assert d.decision == DENY
    assert d.has("DO_NOT_CONTACT")


# ---------------------------------------------------------------------------
# Consent
# ---------------------------------------------------------------------------


def test_unknown_consent_returns_review():
    d = evaluate(_input(consent_basis=None))
    assert d.decision == REVIEW
    assert d.has("CONSENT_UNKNOWN")


def test_unknown_consent_is_never_silent_allow():
    for basis in (None, "unknown"):
        d = evaluate(_input(consent_basis=basis))
        assert d.decision != ALLOW
        assert d.has("CONSENT_UNKNOWN")


def test_blocking_consent_denies():
    d = evaluate(_input(consent_basis="legitimate_interest"))
    assert d.decision == DENY
    assert d.has("CONSENT_BLOCKED")


def test_known_consent_allows():
    d = evaluate(_input(consent_basis="consent"))
    assert d.decision == ALLOW


# ---------------------------------------------------------------------------
# Qualification / Score / Freshness
# ---------------------------------------------------------------------------


def test_qualification_required_denies_unqualified():
    d = evaluate(_input(requires_qualification=True, qualification_status="new"))
    assert d.decision == DENY
    assert d.has("QUALIFICATION_REQUIRED")


def test_qualification_allows_qualified():
    d = evaluate(_input(requires_qualification=True, qualification_status="qualified"))
    assert d.decision == ALLOW


def test_score_below_minimum_denies():
    d = evaluate(_input(min_lead_score=70, lead_score=50))
    assert d.decision == DENY
    assert d.has("SCORE_TOO_LOW")


def test_missing_score_reviews_when_min_required():
    d = evaluate(_input(min_lead_score=70, lead_score=None))
    assert d.decision == REVIEW
    assert d.has("SCORE_UNKNOWN")


def test_score_meets_minimum_allows():
    d = evaluate(_input(min_lead_score=70, lead_score=80))
    assert d.decision == ALLOW


def test_evidence_required_denies_without_evidence():
    d = evaluate(_input(requires_evidence=True, evidence_ids=[]))
    assert d.decision == DENY
    assert d.has("EVIDENCE_REQUIRED")


def test_stale_evidence_denies():
    d = evaluate(_input(min_evidence_freshness_days=7, evidence_freshness_days=100))
    assert d.decision == DENY
    assert d.has("EVIDENCE_STALE")


def test_fresh_evidence_allows():
    d = evaluate(_input(min_evidence_freshness_days=7, evidence_freshness_days=2))
    assert d.decision == ALLOW


# ---------------------------------------------------------------------------
# Channel
# ---------------------------------------------------------------------------


def test_disallowed_channel_denies():
    d = evaluate(_input(channel="telegram"))
    assert d.decision == DENY
    assert d.has("CHANNEL_NOT_ALLOWED")


def test_missing_channel_reviews():
    d = evaluate(_input(channel=None))
    assert d.decision == REVIEW
    assert d.has("CHANNEL_UNSPECIFIED")


# ---------------------------------------------------------------------------
# Campaign state
# ---------------------------------------------------------------------------


def test_campaign_not_running_denies():
    d = evaluate(_input(campaign_running=False))
    assert d.decision == DENY
    assert d.has("CAMPAIGN_NOT_RUNNING")


# ---------------------------------------------------------------------------
# Frequency
# ---------------------------------------------------------------------------


def test_frequency_exceeded_denies():
    d = evaluate(_input(frequency_exceeded=True, frequency_codes=["FREQUENCY_LIMIT"]))
    assert d.decision == DENY
    assert d.has("FREQUENCY_LIMIT")


# ---------------------------------------------------------------------------
# Explainability
# ---------------------------------------------------------------------------


def test_decision_is_explainable():
    d = evaluate(_input(dnc_matches=True, consent_basis=None))
    reasons = d.to_dict()["reasons"]
    assert any(r["code"] == "DO_NOT_CONTACT" for r in reasons)
    assert all(r["severity"] in ("deny", "review") for r in reasons)
    assert d.policy_version == "v1"


def test_high_score_cannot_override_dnc():
    d = evaluate(_input(dnc_matches=True, lead_score=100))
    assert d.decision == DENY
    assert d.has("DO_NOT_CONTACT")


def test_review_accumulates_reasons():
    d = evaluate(_input(consent_basis=None, channel=None, min_lead_score=50, lead_score=None))
    assert d.decision == REVIEW
    assert d.has("CONSENT_UNKNOWN")
    assert d.has("CHANNEL_UNSPECIFIED")
    assert d.has("SCORE_UNKNOWN")