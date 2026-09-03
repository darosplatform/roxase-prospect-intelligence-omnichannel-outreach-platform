import pytest
from httpx import AsyncClient

from app.services.outreach import make_idempotency_key
from tests.conftest import create_company, create_contact, register_tenant

# ---------------------------------------------------------------------------
# Idempotency key unit test
# ---------------------------------------------------------------------------


def test_idempotency_key_stable_and_distinct():
    a = make_idempotency_key("t1", "c1", "l1", "k1", "email", "tpl1", "send-A")
    b = make_idempotency_key("t1", "c1", "l1", "k1", "email", "tpl1", "send-A")
    c = make_idempotency_key("t1", "c1", "l1", "k1", "email", "tpl1", "send-B")
    d = make_idempotency_key("t2", "c1", "l1", "k1", "email", "tpl1", "send-A")
    assert a == b
    assert a != c
    assert a != d


# ---------------------------------------------------------------------------
# Message templates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_template_crud(client: AsyncClient):
    headers = await register_tenant(client, "tpl-a", "tpl@example.com")
    created = await client.post(
        "/api/v1/templates",
        json={"name": "Intro", "channel": "email", "subject": "Hi", "body": "Hello {{first_name}}"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    tpl_id = created.json()["id"]
    assert created.json()["channel"] == "email"

    listed = await client.get("/api/v1/templates", headers=headers)
    assert any(t["id"] == tpl_id for t in listed.json())

    fetched = await client.get(f"/api/v1/templates/{tpl_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Intro"


@pytest.mark.asyncio
async def test_template_invalid_channel_rejected(client: AsyncClient):
    headers = await register_tenant(client, "tpl-bad", "tplbad@example.com")
    resp = await client.post(
        "/api/v1/templates",
        json={"name": "Bad", "channel": "carrier-pigeon", "body": "Hi"},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_template_cross_tenant_isolation(client: AsyncClient):
    h_a = await register_tenant(client, "tpl-isoa", "tplisa@example.com")
    h_b = await register_tenant(client, "tpl-isob", "tplisb@example.com")
    created = await client.post(
        "/api/v1/templates",
        json={"name": "Private", "channel": "email", "body": "Secret"},
        headers=h_a,
    )
    tpl_id = created.json()["id"]
    fetched = await client.get(f"/api/v1/templates/{tpl_id}", headers=h_b)
    assert fetched.status_code == 404


# ---------------------------------------------------------------------------
# Do-not-contact + consent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dnc_crud_and_consent(client: AsyncClient):
    headers = await register_tenant(client, "dnc-a", "dnc@example.com")
    company_id = await create_company(client, headers, "DNC")
    contact_id = await create_contact(client, headers, "DNC")

    company_dnc = await client.post(
        "/api/v1/do-not-contact",
        json={"company_id": company_id, "reason": "no B2B"},
        headers=headers,
    )
    assert company_dnc.status_code == 201, company_dnc.text
    company_dnc_id = company_dnc.json()["id"]

    contact_dnc = await client.post(
        "/api/v1/do-not-contact",
        json={"contact_id": contact_id, "channel": "email", "reason": "opted out"},
        headers=headers,
    )
    assert contact_dnc.status_code == 201
    contact_dnc_id = contact_dnc.json()["id"]

    listed = await client.get("/api/v1/do-not-contact", headers=headers)
    ids = [d["id"] for d in listed.json()]
    assert company_dnc_id in ids and contact_dnc_id in ids

    # consent with allowed basis
    consent = await client.post(
        "/api/v1/consents",
        json={"contact_id": contact_id, "basis": "consent", "channel": "email"},
        headers=headers,
    )
    assert consent.status_code == 200, consent.text
    assert consent.json()["basis"] == "consent"

    # delete dnc
    deleted = await client.delete(
        f"/api/v1/do-not-contact/{contact_dnc_id}", headers=headers
    )
    assert deleted.status_code == 204
    still_listed = await client.get("/api/v1/do-not-contact", headers=headers)
    assert contact_dnc_id not in [d["id"] for d in still_listed.json()]


@pytest.mark.asyncio
async def test_dnc_invalid_basis_rejected(client: AsyncClient):
    headers = await register_tenant(client, "dnc-bad", "dncbad@example.com")
    contact_id = await create_contact(client, headers, "Bad")
    resp = await client.post(
        "/api/v1/consents",
        json={"contact_id": contact_id, "basis": "not-a-basis"},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_dnc_cross_tenant_isolation(client: AsyncClient):
    h_a = await register_tenant(client, "dnc-isoa", "dncisa@example.com")
    h_b = await register_tenant(client, "dnc-isob", "dncisb@example.com")
    contact_a = await create_contact(client, h_a, "A")
    dnc = await client.post(
        "/api/v1/do-not-contact",
        json={"contact_id": contact_a, "channel": "email"},
        headers=h_a,
    )
    dnc_id = dnc.json()["id"]
    fetched = await client.get(f"/api/v1/do-not-contact/{dnc_id}", headers=h_b)
    assert fetched.status_code == 404