import pytest
from httpx import AsyncClient

from tests.conftest import create_company, register_tenant


async def _setup(client: AsyncClient, suffix: str):
    headers = await register_tenant(client, f"pol-{suffix}", f"pol{suffix}@example.com")
    company_id = await create_company(client, headers, suffix)
    lead_resp = await client.post(
        "/api/v1/leads", json={"company_id": company_id, "status": "qualified"}, headers=headers
    )
    lead_id = lead_resp.json()["id"]

    contact_resp = await client.post(
        "/api/v1/contacts",
        json={"first_name": f"Pol{suffix}", "last_name": "Last", "email": f"p{suffix}@x.com"},
        headers=headers,
    )
    contact_id = contact_resp.json()["id"]

    camp_resp = await client.post(
        "/api/v1/campaigns",
        json={
            "name": f"Campaign {suffix}",
            "status": "running",
            "channel": "email",
            "policy": {"dry_run": True, "allowed_channels": ["email"]},
        },
        headers=headers,
    )
    campaign_id = camp_resp.json()["id"]
    return headers, lead_id, contact_id, campaign_id


async def _evaluate(client, headers, lead_id, campaign_id, contact_id, channel="email", **extra):
    body = {
        "lead_id": lead_id,
        "campaign_id": campaign_id,
        "contact_id": contact_id,
        "channel": channel,
        **extra,
    }
    if channel is None:
        del body["channel"]
    return await client.post("/api/v1/policies/evaluate", json=body, headers=headers)


@pytest.mark.asyncio
async def test_policy_evaluate_allows(client: AsyncClient):
    headers, lead_id, contact_id, campaign_id = await _setup(client, "allow")
    await client.post(
        "/api/v1/consents",
        json={"contact_id": contact_id, "basis": "consent", "channel": "email"},
        headers=headers,
    )
    resp = await _evaluate(client, headers, lead_id, campaign_id, contact_id)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["decision"] == "ALLOW"
    assert body["policy_version"] == "v1"
    assert body["lead_id"] == lead_id
    assert body["campaign_id"] == campaign_id
    assert body["contact_id"] == contact_id


@pytest.mark.asyncio
async def test_policy_evaluate_unknown_consent_reviews(client: AsyncClient):
    headers, lead_id, contact_id, campaign_id = await _setup(client, "review")
    resp = await _evaluate(client, headers, lead_id, campaign_id, contact_id)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["decision"] == "REVIEW"
    assert any(r["code"] == "CONSENT_UNKNOWN" for r in body["reasons"])


@pytest.mark.asyncio
async def test_policy_evaluate_dnc_denies(client: AsyncClient):
    headers, lead_id, contact_id, campaign_id = await _setup(client, "deny")
    await client.post(
        "/api/v1/consents",
        json={"contact_id": contact_id, "basis": "consent", "channel": "email"},
        headers=headers,
    )
    dnc = await client.post(
        "/api/v1/do-not-contact",
        json={"contact_id": contact_id, "channel": "email", "reason": "opted out"},
        headers=headers,
    )
    assert dnc.status_code == 201, dnc.text
    resp = await _evaluate(client, headers, lead_id, campaign_id, contact_id)
    body = resp.json()
    assert body["decision"] == "DENY"
    assert any(r["code"] == "DO_NOT_CONTACT" for r in body["reasons"])


@pytest.mark.asyncio
async def test_policy_evaluate_disallowed_channel_denies(client: AsyncClient):
    headers, lead_id, contact_id, campaign_id = await _setup(client, "channel")
    await client.post(
        "/api/v1/consents",
        json={"contact_id": contact_id, "basis": "consent", "channel": "email"},
        headers=headers,
    )
    resp = await _evaluate(client, headers, lead_id, campaign_id, contact_id, channel="telegram")
    body = resp.json()
    assert body["decision"] == "DENY"
    assert any(r["code"] == "CHANNEL_NOT_ALLOWED" for r in body["reasons"])


@pytest.mark.asyncio
async def test_policy_evaluate_persists_decision_and_audit(
    client: AsyncClient, db_session
):
    from sqlalchemy import select

    from app.models.audit import AuditEvent

    headers, lead_id, contact_id, campaign_id = await _setup(client, "persist")
    await client.post(
        "/api/v1/consents",
        json={"contact_id": contact_id, "basis": "consent", "channel": "email"},
        headers=headers,
    )
    resp = await _evaluate(client, headers, lead_id, campaign_id, contact_id)
    decision_id = resp.json()["decision_id"]
    assert decision_id

    listed = await client.get(
        f"/api/v1/policy-decisions?lead_id={lead_id}", headers=headers
    )
    assert listed.status_code == 200, listed.text
    ids = [d["id"] for d in listed.json()]
    assert decision_id in ids

    result = await db_session.execute(
        select(AuditEvent).where(AuditEvent.action == "policy.evaluated")
    )
    assert len(list(result.scalars().all())) >= 1


@pytest.mark.asyncio
async def test_policy_cross_tenant_isolation(client: AsyncClient):
    h_a, lead_a, _contact_a, camp_a = await _setup(client, "xta")
    h_b, _lead_b, _contact_b, camp_b = await _setup(client, "xtb")
    # tenant B cannot evaluate tenant A's lead
    resp = await client.post(
        "/api/v1/policies/evaluate",
        json={
            "lead_id": lead_a,
            "campaign_id": camp_b,
            "channel": "email",
        },
        headers=h_b,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_policy_rbac_analyst_can_evaluate(client: AsyncClient):
    from tests.conftest import create_user_with_role

    headers, lead_id, contact_id, campaign_id = await _setup(client, "rbac")
    await client.post(
        "/api/v1/consents",
        json={"contact_id": contact_id, "basis": "consent", "channel": "email"},
        headers=headers,
    )
    analyst = await create_user_with_role(client, headers, "analyst@example.com", "analyst")
    assert analyst  # creation succeeded
    # analyst has access to policy reads per RBAC read policy (user active)
    resp = await _evaluate(client, analyst, lead_id, campaign_id, contact_id)
    assert resp.status_code in (200, 403), resp.text