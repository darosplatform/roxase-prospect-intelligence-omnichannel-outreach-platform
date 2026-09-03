import pytest
from httpx import AsyncClient

from tests.conftest import create_company, register_tenant


@pytest.mark.asyncio
async def test_create_opportunity(company_auth):
    client, headers, company_id = company_auth
    payload = {
        "company_id": company_id,
        "name": "Expansion deal",
        "stage": "qualified",
        "value": 100000.0,
        "currency": "EUR",
        "probability": 0.6,
    }
    response = await client.post("/api/v1/opportunities", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Expansion deal"
    assert data["stage"] == "qualified"
    assert data["currency"] == "EUR"
    assert data["probability"] == 0.6


@pytest.mark.asyncio
async def test_list_and_get_opportunity(company_auth):
    client, headers, company_id = company_auth
    create_resp = await client.post(
        "/api/v1/opportunities",
        json={"company_id": company_id, "name": "Deal"},
        headers=headers,
    )
    opp_id = create_resp.json()["id"]

    list_resp = await client.get("/api/v1/opportunities", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    get_resp = await client.get(f"/api/v1/opportunities/{opp_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Deal"


@pytest.mark.asyncio
async def test_get_opportunity_invalid_stage(company_auth):
    client, headers, company_id = company_auth
    response = await client.post(
        "/api/v1/opportunities",
        json={"company_id": company_id, "name": "Bad", "stage": "wonky"},
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_opportunity_rejects_foreign_company(company_auth, client: AsyncClient):
    client, headers, _ = company_auth
    other_headers = await register_tenant(client, "tenant-opp-other", "oppother@example.com")
    other_company = await create_company(client, other_headers, "OppOther")
    response = await client.post(
        "/api/v1/opportunities",
        json={"company_id": other_company, "name": "Foreign"},
        headers=headers,
    )
    assert response.status_code == 404