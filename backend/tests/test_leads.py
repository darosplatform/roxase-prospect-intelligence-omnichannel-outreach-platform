import pytest


@pytest.mark.asyncio
async def test_create_lead(auth_client):
    client, headers = auth_client
    payload = {
        "score": 75,
        "status": "new",
        "qualification_reason": "High intent signal detected",
    }
    response = await client.post("/api/v1/leads", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["score"] == 75
    assert data["status"] == "new"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_leads(auth_client):
    client, headers = auth_client
    response = await client.get("/api/v1/leads", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)