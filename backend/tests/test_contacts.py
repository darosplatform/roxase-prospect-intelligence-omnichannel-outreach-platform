import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_contact(client: AsyncClient):
    payload = {
        "first_name": "Jean",
        "last_name": "Dupont",
        "email": "jean@example.com",
        "job_title": "CTO",
        "source": "manual",
    }
    response = await client.post("/api/v1/contacts", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["first_name"] == "Jean"
    assert data["email"] == "jean@example.com"
    assert "id" in data
