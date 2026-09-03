import pytest


@pytest.mark.asyncio
async def test_create_company(auth_client):
    client, headers = auth_client
    payload = {
        "legal_name": "Acme Corp",
        "domain": "acme.com",
        "country": "FR",
        "industry": "Technology",
        "employee_count": 50,
        "source": "manual",
    }
    response = await client.post("/api/v1/companies", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["legal_name"] == "Acme Corp"
    assert data["domain"] == "acme.com"
    assert data["country"] == "FR"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_companies(auth_client):
    client, headers = auth_client
    response = await client.get("/api/v1/companies", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_get_company(auth_client):
    client, headers = auth_client
    create_resp = await client.post(
        "/api/v1/companies",
        json={"legal_name": "TestCo", "domain": "test.co"},
        headers=headers,
    )
    company_id = create_resp.json()["id"]
    response = await client.get(f"/api/v1/companies/{company_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["legal_name"] == "TestCo"