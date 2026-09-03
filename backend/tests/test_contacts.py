import pytest


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