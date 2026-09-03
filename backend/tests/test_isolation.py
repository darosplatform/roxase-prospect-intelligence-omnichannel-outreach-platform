import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_tenant_isolation(client: AsyncClient):
    a_resp = await client.post(
        "/api/v1/auth/register",
        params={"slug": "tenant-alpha"},
        json={"email": "alpha@example.com", "password": "supersecret"},
    )
    b_resp = await client.post(
        "/api/v1/auth/register",
        params={"slug": "tenant-beta"},
        json={"email": "beta@example.com", "password": "supersecret"},
    )
    a_token = a_resp.json()["access_token"]
    b_token = b_resp.json()["access_token"]
    a_headers = {"Authorization": f"Bearer {a_token}"}
    b_headers = {"Authorization": f"Bearer {b_token}"}

    a_create = await client.post(
        "/api/v1/companies",
        json={"legal_name": "AlphaCo", "domain": "alpha.com"},
        headers=a_headers,
    )
    assert a_create.status_code == 201
    a_company = a_create.json()

    b_list = await client.get("/api/v1/companies", headers=b_headers)
    assert b_list.status_code == 200
    assert b_list.json() == [], f"Tenant B should not see tenant A's data, got: {b_list.json()}"

    a_list = await client.get("/api/v1/companies", headers=a_headers)
    assert len(a_list.json()) == 1
    assert a_list.json()[0]["id"] == a_company["id"]

    b_get = await client.get(f"/api/v1/companies/{a_company['id']}", headers=b_headers)
    assert b_get.status_code == 404