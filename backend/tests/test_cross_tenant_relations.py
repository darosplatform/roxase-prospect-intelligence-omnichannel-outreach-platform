import pytest
from httpx import AsyncClient

from tests.conftest import create_company, create_contact, create_lead, register_tenant


def user_id_from_token(token: str):
    from app.core.security import decode_token

    payload = decode_token(token)
    assert payload is not None
    return payload["sub"]


async def _two_tenants(client, suffix):
    headers_a = await register_tenant(client, f"rel-a-{suffix}", f"rela{suffix}@example.com")
    headers_b = await register_tenant(client, f"rel-b-{suffix}", f"relb{suffix}@example.com")
    company_a = await create_company(client, headers_a, f"A{suffix}")
    company_b = await create_company(client, headers_b, f"B{suffix}")
    user_b_id = user_id_from_token(headers_b["Authorization"].split(" ")[1])
    return headers_a, headers_b, company_a, company_b, user_b_id


@pytest.mark.asyncio
async def test_opportunity_rejects_foreign_contact(client: AsyncClient):
    headers_a, headers_b, company_a, _, _ = await _two_tenants(client, "oppcontact")
    contact_b = await create_contact(client, headers_b, "B")

    resp = await client.post(
        "/api/v1/opportunities",
        json={"company_id": company_a, "contact_id": contact_b, "name": "Deal"},
        headers=headers_a,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_opportunity_rejects_foreign_lead(client: AsyncClient):
    headers_a, headers_b, company_a, _, _ = await _two_tenants(client, "pplead")
    lead_b = await create_lead(client, headers_b, "B")

    resp = await client.post(
        "/api/v1/opportunities",
        json={"company_id": company_a, "lead_id": lead_b, "name": "Deal"},
        headers=headers_a,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_opportunity_rejects_foreign_owner_user(client: AsyncClient):
    headers_a, _, company_a, _, user_b_id = await _two_tenants(client, "ppowner")

    resp = await client.post(
        "/api/v1/opportunities",
        json={"company_id": company_a, "owner_user_id": user_b_id, "name": "Deal"},
        headers=headers_a,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_task_rejects_foreign_assigned_user(client: AsyncClient):
    headers_a, _, _, _, user_b_id = await _two_tenants(client, "taskassigned")

    resp = await client.post(
        "/api/v1/tasks",
        json={"title": "Task", "assigned_to": user_b_id},
        headers=headers_a,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_activity_rejects_foreign_company(client: AsyncClient):
    headers_a, _, _, company_b, _ = await _two_tenants(client, "actcompany")

    resp = await client.post(
        "/api/v1/activities",
        json={"company_id": company_b, "activity_type": "email", "subject": "x"},
        headers=headers_a,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_note_rejects_foreign_company(client: AsyncClient):
    headers_a, _, _, company_b, _ = await _two_tenants(client, "notecompany")

    resp = await client.post(
        "/api/v1/notes",
        json={"company_id": company_b, "content": "secret"},
        headers=headers_a,
    )
    assert resp.status_code == 404