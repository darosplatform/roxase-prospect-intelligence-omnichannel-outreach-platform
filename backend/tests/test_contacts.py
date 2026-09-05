import pytest

from tests.conftest import create_company, register_tenant


@pytest.mark.asyncio
async def test_create_contact(auth_client):
    client, headers = auth_client
    payload = {
        "first_name": "Jean",
        "last_name": "Dupont",
        "email": "jean@example.com",
        "job_title": "CTO",
        "source": "manual",
    }
    response = await client.post("/api/v1/contacts", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["first_name"] == "Jean"
    assert data["email"] == "jean@example.com"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_contact_rejects_company_from_another_tenant(client):
    headers_a = await register_tenant(client, "contacts-tenant-a", "a@contacts-a.example")
    headers_b = await register_tenant(client, "contacts-tenant-b", "b@contacts-b.example")
    company_b = await create_company(client, headers_b, "B")

    response = await client.post(
        "/api/v1/contacts",
        json={"first_name": "Cross", "company_id": company_b},
        headers=headers_a,
    )
    assert response.status_code == 404