"""End-to-end prospect pipeline: Company -> Contact -> Evidence -> Signal
-> Lead -> Qualification -> Score -> Campaign -> Policy -> OutreachRequest
-> MockProvider -> Audit, plus the mandated negative scenarios."""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.services.providers import registry
from tests.conftest import register_tenant


async def _build_pipeline(
    client: AsyncClient,
    suffix: str,
    signal_detected_at: str | None = None,
    record_consent: bool = True,
    **campaign_policy,
):
    """Walk the full prospect chain and return all ids."""
    headers = await register_tenant(client, f"e2e-{suffix}", f"e2e{suffix}@example.com")

    company = await client.post(
        "/api/v1/companies",
        json={"legal_name": f"Pipeline {suffix}", "domain": f"e2e{suffix}.com"},
        headers=headers,
    )
    company_id = company.json()["id"]

    contact = await client.post(
        "/api/v1/contacts",
        json={
            "company_id": company_id,
            "first_name": "Erin",
            "last_name": f"E2E{suffix}",
            "email": f"erin{suffix}@e2e.com",
            "job_title": "CTO",
        },
        headers=headers,
    )
    contact_id = contact.json()["id"]

    evidence = await client.post(
        "/api/v1/evidence",
        json={
            "company_id": company_id,
            "source_url": f"https://e2e{suffix}.com/article",
            "source_name": "NewsWire",
            "evidence_type": "news",
            "title": f"Pipeline {suffix} raised Series A",
        },
        headers=headers,
    )
    evidence_id = evidence.json()["id"]

    signal_payload = {
        "company_id": company_id,
        "evidence_id": evidence_id,
        "signal_type": "funding",
        "title": f"Funding {suffix}",
        "confidence": 1.0,
        "detected_at": signal_detected_at or datetime.now(UTC).isoformat(),
    }
    signal = await client.post("/api/v1/signals", json=signal_payload, headers=headers)
    signal_id = signal.json()["id"]

    lead = await client.post(
        "/api/v1/leads", json={"company_id": company_id, "status": "new"}, headers=headers
    )
    lead_id = lead.json()["id"]

    qualify = await client.post(
        f"/api/v1/leads/{lead_id}/qualify",
        json={"status": "qualified", "evidence_ids": [evidence_id]},
        headers=headers,
    )
    assert qualify.status_code == 200, qualify.text

    score = await client.post(f"/api/v1/leads/{lead_id}/score", headers=headers)
    assert score.status_code == 200, score.text
    score_val = score.json()["score"]
    assert score_val and 0 < score_val <= 100

    default_policy = {
        "dry_run": True,
        "allowed_channels": ["email"],
        "min_lead_score": 1,
        "require_qualification": True,
        "require_evidence": True,
    }
    default_policy.update(campaign_policy)
    campaign = await client.post(
        "/api/v1/campaigns",
        json={
            "name": f"Campaign {suffix}",
            "status": "running",
            "channel": "email",
            "policy": default_policy,
        },
        headers=headers,
    )
    assert campaign.status_code == 201, campaign.text
    campaign_id = campaign.json()["id"]

    template = await client.post(
        "/api/v1/templates",
        json={"name": f"Tmp {suffix}", "channel": "email", "body": "Hi {{first_name}}"},
        headers=headers,
    )
    template_id = template.json()["id"]

    if record_consent:
        await client.post(
            "/api/v1/consents",
            json={"contact_id": contact_id, "basis": "consent", "channel": "email"},
            headers=headers,
        )

    return {
        "headers": headers,
        "company_id": company_id,
        "contact_id": contact_id,
        "evidence_id": evidence_id,
        "signal_id": signal_id,
        "lead_id": lead_id,
        "campaign_id": campaign_id,
        "template_id": template_id,
    }


def _email_calls() -> int:
    return len(registry.provider_for("email").calls)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_full_pipeline_allow_and_dry_run_send(client: AsyncClient):
    ctx = await _build_pipeline(client, "happy")

    # Policy evaluation: ALLOW (qualified, scored, evidenced, consent, running)
    ev = await client.post(
        "/api/v1/policies/evaluate",
        json={
            "lead_id": ctx["lead_id"],
            "campaign_id": ctx["campaign_id"],
            "contact_id": ctx["contact_id"],
            "channel": "email",
        },
        headers=ctx["headers"],
    )
    assert ev.status_code == 200, ev.text
    assert ev.json()["decision"] == "ALLOW"
    assert ev.json()["policy_version"] == "v1"
    # evidence traced on the decision
    assert str(ctx["evidence_id"]) in ev.json()["evidence_ids"]

    # Create the outreach request (idempotent)
    or_create = await client.post(
        "/api/v1/outreach",
        json={
            "lead_id": ctx["lead_id"],
            "campaign_id": ctx["campaign_id"],
            "contact_id": ctx["contact_id"],
            "channel": "email",
            "template_id": ctx["template_id"],
        },
        headers=ctx["headers"],
    )
    assert or_create.status_code == 201, or_create.text
    outreach_id = or_create.json()["id"]
    assert or_create.json()["status"] == "approved"

    # Dispatch in dry-run: simulated send, ZERO real provider calls
    before = _email_calls()
    dispatched = await client.post(
        f"/api/v1/outreach/{outreach_id}/dispatch", headers=ctx["headers"]
    )
    assert dispatched.status_code == 200, dispatched.text
    assert dispatched.json()["status"] == "sent"
    assert dispatched.json()["provider_message_id"].startswith("dry_run:")
    assert _email_calls() == before  # no real send


@pytest.mark.asyncio
async def test_e2e_search_company_via_pipeline(client: AsyncClient):
    ctx = await _build_pipeline(client, "find")
    # company created by the pipeline is discoverable by its legal name
    res = await client.get("/api/v1/companies?q=pipeline+find", headers=ctx["headers"])
    assert res.status_code == 200
    assert any(c["id"] == ctx["company_id"] for c in res.json())


# ---------------------------------------------------------------------------
# Negative scenarios
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_dnc_denies(client: AsyncClient):
    ctx = await _build_pipeline(client, "dnc")
    await client.post(
        "/api/v1/do-not-contact",
        json={"contact_id": ctx["contact_id"], "channel": "email", "reason": "opt out"},
        headers=ctx["headers"],
    )
    ev = await client.post(
        "/api/v1/policies/evaluate",
        json={
            "lead_id": ctx["lead_id"],
            "campaign_id": ctx["campaign_id"],
            "contact_id": ctx["contact_id"],
            "channel": "email",
        },
        headers=ctx["headers"],
    )
    assert ev.json()["decision"] == "DENY"
    assert any(r["code"] == "DO_NOT_CONTACT" for r in ev.json()["reasons"])

    or_create = await client.post(
        "/api/v1/outreach",
        json={
            "lead_id": ctx["lead_id"],
            "campaign_id": ctx["campaign_id"],
            "contact_id": ctx["contact_id"],
            "channel": "email",
            "template_id": ctx["template_id"],
        },
        headers=ctx["headers"],
    )
    assert or_create.status_code == 201
    assert or_create.json()["status"] == "denied"
    dispatch = await client.post(
        f"/api/v1/outreach/{or_create.json()['id']}/dispatch", headers=ctx["headers"]
    )
    assert dispatch.status_code == 409  # denied never reaches a provider


@pytest.mark.asyncio
async def test_e2e_unknown_consent_reviews(client: AsyncClient):
    # No consent recorded -> consent_basis stays None -> REVIEW
    ctx = await _build_pipeline(client, "review", record_consent=False)
    ev = await client.post(
        "/api/v1/policies/evaluate",
        json={
            "lead_id": ctx["lead_id"],
            "campaign_id": ctx["campaign_id"],
            "contact_id": ctx["contact_id"],
            "channel": "email",
        },
        headers=ctx["headers"],
    )
    assert ev.json()["decision"] == "REVIEW"
    assert any(r["code"] == "CONSENT_UNKNOWN" for r in ev.json()["reasons"])


@pytest.mark.asyncio
async def test_e2e_low_score_denies(client: AsyncClient):
    # min_lead_score above the scored lead -> DENY
    ctx = await _build_pipeline(client, "lowscore", min_lead_score=90)
    ev = await client.post(
        "/api/v1/policies/evaluate",
        json={
            "lead_id": ctx["lead_id"],
            "campaign_id": ctx["campaign_id"],
            "contact_id": ctx["contact_id"],
            "channel": "email",
        },
        headers=ctx["headers"],
    )
    assert ev.json()["decision"] == "DENY"
    assert any(r["code"] == "SCORE_TOO_LOW" for r in ev.json()["reasons"])


@pytest.mark.asyncio
async def test_e2e_stale_evidence_denies(client: AsyncClient):
    # Build the lead with evidence that is far older than the allowed window.
    ctx = await _build_pipeline(
        client,
        "stale",
        signal_detected_at="2020-01-01T00:00:00Z",
        min_evidence_freshness_days=5,
    )
    ev = await client.post(
        "/api/v1/policies/evaluate",
        json={
            "lead_id": ctx["lead_id"],
            "campaign_id": ctx["campaign_id"],
            "contact_id": ctx["contact_id"],
            "channel": "email",
        },
        headers=ctx["headers"],
    )
    assert ev.json()["decision"] == "DENY"
    assert any(r["code"] == "EVIDENCE_STALE" for r in ev.json()["reasons"])


@pytest.mark.asyncio
async def test_e2e_frequency_exceeded_denies(client: AsyncClient):
    ctx = await _build_pipeline(client, "freq", max_contact_per_day=2)
    await client.post(
        "/api/v1/consents",
        json={"contact_id": ctx["contact_id"], "basis": "consent", "channel": "email"},
        headers=ctx["headers"],
    )
    # first two distinct sends are dispatched (counted as sent)
    dispatched_ids = []
    for i in range(2):
        r = await client.post(
            "/api/v1/outreach",
            json={
                "lead_id": ctx["lead_id"],
                "campaign_id": ctx["campaign_id"],
                "contact_id": ctx["contact_id"],
                "channel": "email",
                "template_id": ctx["template_id"],
                "logical_send_id": f"send-{i}",
            },
            headers=ctx["headers"],
        )
        assert r.status_code == 201, r.text
        assert r.json()["status"] == "approved"
        dispatched_ids.append(r.json()["id"])
        d = await client.post(
            f"/api/v1/outreach/{r.json()['id']}/dispatch", headers=ctx["headers"]
        )
        assert d.status_code == 200, d.text
        assert d.json()["status"] == "sent"

    assert len(set(dispatched_ids)) == 2  # distinct messages

    # third (distinct logical send) is evaluated against the frequency limit
    third = await client.post(
        "/api/v1/outreach",
        json={
            "lead_id": ctx["lead_id"],
            "campaign_id": ctx["campaign_id"],
            "contact_id": ctx["contact_id"],
            "channel": "email",
            "template_id": ctx["template_id"],
            "logical_send_id": "send-2",
        },
        headers=ctx["headers"],
    )
    out = third.json()
    assert out["status"] == "denied"


@pytest.mark.asyncio
async def test_e2e_duplicate_request_is_idempotent(client: AsyncClient):
    ctx = await _build_pipeline(client, "dupe")
    payload = {
        "lead_id": ctx["lead_id"],
        "campaign_id": ctx["campaign_id"],
        "contact_id": ctx["contact_id"],
        "channel": "email",
        "template_id": ctx["template_id"],
    }
    a = await client.post("/api/v1/outreach", json=payload, headers=ctx["headers"])
    b = await client.post("/api/v1/outreach", json=payload, headers=ctx["headers"])
    assert a.status_code == 201 and b.status_code == 201
    assert a.json()["id"] == b.json()["id"]
    assert a.json()["idempotency_key"] == b.json()["idempotency_key"]

    listed = await client.get("/api/v1/outreach", headers=ctx["headers"])
    assert len(listed.json()) == 1  # no duplicate send


@pytest.mark.asyncio
async def test_e2e_kill_switch_blocks_send(client: AsyncClient):
    ctx = await _build_pipeline(client, "kill")
    # kill switch ON (outreach_enabled=False) -> OUTREACH_DISABLED deny
    d = await _evaluate_with_switch(client, ctx, enabled=False)
    assert d == "DENY"
    # kill switch OFF (outreach_enabled=True) -> normal ALLOW
    d2 = await _evaluate_with_switch(client, ctx, enabled=True)
    assert d2 == "ALLOW"


async def _evaluate_with_switch(client, ctx, enabled) -> str:
    """Evaluate while toggling the global kill switch (patch settings)."""
    from app.core.config import settings

    original = settings.outreach_enabled
    settings.outreach_enabled = enabled
    try:
        ev = await client.post(
            "/api/v1/policies/evaluate",
            json={
                "lead_id": ctx["lead_id"],
                "campaign_id": ctx["campaign_id"],
                "contact_id": ctx["contact_id"],
                "channel": "email",
            },
            headers=ctx["headers"],
        )
        return ev.json()["decision"]
    finally:
        settings.outreach_enabled = original


@pytest.mark.asyncio
async def test_e2e_cross_tenant_isolation(client: AsyncClient):
    ctx = await _build_pipeline(client, "xtenant")
    h_other = await register_tenant(client, "e2e-other", "e2eother@example.com")
    # other tenant cannot read the decision list of the first
    resp = await client.get(
        f"/api/v1/policy-decisions?lead_id={ctx['lead_id']}", headers=h_other
    )
    assert resp.status_code == 200
    assert resp.json() == []
    # other tenant cannot evaluate first tenant's lead
    ev = await client.post(
        "/api/v1/policies/evaluate",
        json={
            "lead_id": ctx["lead_id"],
            "campaign_id": ctx["campaign_id"],
            "channel": "email",
        },
        headers=h_other,
    )
    assert ev.status_code == 404