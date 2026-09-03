import pytest
from httpx import AsyncClient

from tests.conftest import create_company, register_tenant


@pytest.mark.asyncio
async def test_create_signal(company_auth):
    client, headers, company_id = company_auth
    payload = {
        "company_id": company_id,
        "signal_type": "funding",
        "title": "Series B raised",
        "confidence": 0.9,
    }
    response = await client.post("/api/v1/signals", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["signal_type"] == "funding"
    assert data["confidence"] == 0.9
    assert data["company_id"] == company_id
    assert "tenant_id" in data


@pytest.mark.asyncio
async def test_list_signals(company_auth):
    client, headers, company_id = company_auth
    await client.post(
        "/api/v1/signals",
        json={"company_id": company_id, "signal_type": "hiring"},
        headers=headers,
    )
    response = await client.get("/api/v1/signals", headers=headers)
    assert response.status_code == 200
    signals = response.json()
    assert len(signals) == 1
    assert signals[0]["signal_type"] == "hiring"


@pytest.mark.asyncio
async def test_create_signal_rejects_foreign_company(company_auth, client: AsyncClient):
    client, headers, _ = company_auth
    other_headers = await register_tenant(client, "tenant-other", "other@example.com")
    other_company = await create_company(client, other_headers, "Other")
    response = await client.post(
        "/api/v1/signals",
        json={"company_id": other_company, "signal_type": "funding"},
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_signal_rejects_invalid_type(company_auth):
    client, headers, company_id = company_auth
    response = await client.post(
        "/api/v1/signals",
        json={"company_id": company_id, "signal_type": "not_a_real_type"},
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_signal_rejects_confidence_out_of_range(company_auth):
    client, headers, company_id = company_auth
    response = await client.post(
        "/api/v1/signals",
        json={"company_id": company_id, "signal_type": "funding", "confidence": 1.5},
        headers=headers,
    )
    assert response.status_code == 422