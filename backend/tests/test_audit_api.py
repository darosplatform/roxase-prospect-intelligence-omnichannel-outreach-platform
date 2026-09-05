"""GET /api/v1/audit: read-only, tenant-scoped, filterable listing of
already-recorded audit events."""

import pytest
from httpx import AsyncClient

from tests.conftest import create_company, register_tenant


@pytest.mark.asyncio
async def test_list_audit_events_after_creating_a_signal(client: AsyncClient):
    headers = await register_tenant(client, "audit-api", "audit-api@example.com")
    company_id = await create_company(client, headers, "audit")
    await client.post(
        "/api/v1/signals",
        json={"company_id": company_id, "signal_type": "hiring", "confidence": 1.0},
        headers=headers,
    )

    resp = await client.get("/api/v1/audit", headers=headers)
    assert resp.status_code == 200, resp.text
    events = resp.json()
    assert any(e["action"] == "signal.created" for e in events)


@pytest.mark.asyncio
async def test_list_audit_events_filters_by_entity_type(client: AsyncClient):
    headers = await register_tenant(client, "audit-filter", "audit-filter@example.com")
    company_id = await create_company(client, headers, "filt")
    await client.post(
        "/api/v1/signals",
        json={"company_id": company_id, "signal_type": "hiring", "confidence": 1.0},
        headers=headers,
    )

    resp = await client.get(
        "/api/v1/audit", params={"entity_type": "signal"}, headers=headers
    )
    assert resp.status_code == 200
    assert all(e["entity_type"] == "signal" for e in resp.json())

    resp2 = await client.get(
        "/api/v1/audit", params={"entity_type": "campaign"}, headers=headers
    )
    assert resp2.json() == []


@pytest.mark.asyncio
async def test_audit_events_are_tenant_isolated(client: AsyncClient):
    a_headers = await register_tenant(client, "audit-iso-a", "audit-iso-a@example.com")
    b_headers = await register_tenant(client, "audit-iso-b", "audit-iso-b@example.com")
    company_id = await create_company(client, a_headers, "iso")
    await client.post(
        "/api/v1/signals",
        json={"company_id": company_id, "signal_type": "hiring", "confidence": 1.0},
        headers=a_headers,
    )

    b_events = await client.get("/api/v1/audit", headers=b_headers)
    assert b_events.json() == []
