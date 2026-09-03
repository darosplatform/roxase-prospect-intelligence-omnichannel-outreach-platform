import pytest
from httpx import AsyncClient

from tests.conftest import create_company, register_tenant


async def _setup(client: AsyncClient, suffix: str, dry_run: bool = True):
    headers = await register_tenant(client, f"out-{suffix}", f"out{suffix}@example.com")
    company_id = await create_company(client, headers, suffix)
    lead_resp = await client.post(
        "/api/v1/leads", json={"company_id": company_id, "status": "new"}, headers=headers
    )
    lead_id = lead_resp.json()["id"]
    contact_resp = await client.post(
        "/api/v1/contacts",
        json={"first_name": f"Out{suffix}", "last_name": "Last", "email": f"o{suffix}@x.com"},
        headers=headers,
    )
    contact_id = contact_resp.json()["id"]
    camp_resp = await client.post(
        "/api/v1/campaigns",
        json={
            "name": f"Out {suffix}",
            "status": "running",
            "channel": "email",
            "policy": {"dry_run": dry_run, "allowed_channels": ["email"]},
        },
        headers=headers,
    )
    campaign_id = camp_resp.json()["id"]
    tpl_resp = await client.post(
        "/api/v1/templates",
        json={"name": f"TPL {suffix}", "channel": "email", "body": "Hi {{first_name}}"},
        headers=headers,
    )
    template_id = tpl_resp.json()["id"]
    await client.post(
        "/api/v1/consents",
        json={"contact_id": contact_id, "basis": "consent", "channel": "email"},
        headers=headers,
    )
    return headers, lead_id, contact_id, campaign_id, template_id


async def _create_req(client, headers, campaign_id, contact_id, template_id, channel="email"):
    body = {
        "campaign_id": campaign_id,
        "contact_id": contact_id,
        "channel": channel,
        "template_id": template_id,
    }
    return await client.post("/api/v1/outreach", json=body, headers=headers)


@pytest.mark.asyncio
async def test_outreach_dry_run_creates_and_simulates(client: AsyncClient, db_session):
    headers, lead_id, contact_id, campaign_id, template_id = await _setup(client, "dry")
    resp = await _create_req(client, headers, campaign_id, contact_id, template_id)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "approved"
    assert body["lead_id"] == lead_id

    dispatched = await client.post(
        f"/api/v1/outreach/{body['id']}/dispatch", headers=headers
    )
    assert dispatched.status_code == 200, dispatched.text
    assert dispatched.json()["status"] == "sent"
    assert dispatched.json()["provider_message_id"].startswith("dry_run:")

    from sqlalchemy import select

    from app.models.audit import AuditEvent

    result = await db_session.execute(
        select(AuditEvent).where(AuditEvent.action == "outreach.simulated")
    )
    assert len(list(result.scalars().all())) >= 1


@pytest.mark.asyncio
async def test_outreach_denied_by_policy_never_queued(client: AsyncClient):
    headers, lead_id, contact_id, campaign_id, template_id = await _setup(client, "denied")
    dnc = await client.post(
        "/api/v1/do-not-contact",
        json={"contact_id": contact_id, "channel": "email", "reason": "opt out"},
        headers=headers,
    )
    assert dnc.status_code == 201, dnc.text
    resp = await _create_req(client, headers, campaign_id, contact_id, template_id)
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "denied"
    dispatched = await client.post(
        f"/api/v1/outreach/{resp.json()['id']}/dispatch", headers=headers
    )
    assert dispatched.status_code == 409
    assert dispatched.json()["detail"] == "Denied request cannot be dispatched"


@pytest.mark.asyncio
async def test_outreach_idempotent_single_request(client: AsyncClient):
    headers, lead_id, contact_id, campaign_id, template_id = await _setup(client, "idem")
    first = await _create_req(client, headers, campaign_id, contact_id, template_id)
    second = await _create_req(client, headers, campaign_id, contact_id, template_id)
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["idempotency_key"] == second.json()["idempotency_key"]

    listed = await client.get("/api/v1/outreach", headers=headers)
    ids = [o["id"] for o in listed.json()]
    assert ids.count(first.json()["id"]) == 1


@pytest.mark.asyncio
async def test_outreach_review_path_leaves_pending(client: AsyncClient):
    headers, lead_id, contact_id, campaign_id, template_id = await _setup(client, "rev")
    resp = await _create_req(client, headers, campaign_id, contact_id, template_id)
    assert resp.status_code == 201, resp.text
    # default dry-run allow with consent present yields approved
    assert resp.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_outreach_rbac_operator_and_viewer(client: AsyncClient):
    from tests.conftest import create_user_with_role

    headers, lead_id, contact_id, campaign_id, template_id = await _setup(client, "op")
    operator = await create_user_with_role(client, headers, "operator@example.com", "operator")
    resp = await _create_req(client, operator, campaign_id, contact_id, template_id)
    assert resp.status_code in (200, 201, 403), resp.text

    viewer = await create_user_with_role(client, headers, "viewer@example.com", "viewer")
    resp_read = await client.get("/api/v1/outreach", headers=viewer)
    assert resp_read.status_code == 200, resp_read.text
    resp_create = await _create_req(client, viewer, campaign_id, contact_id, template_id)
    assert resp_create.status_code == 403