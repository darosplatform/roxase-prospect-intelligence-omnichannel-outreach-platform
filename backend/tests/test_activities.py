import pytest


@pytest.mark.asyncio
async def test_create_activity(company_auth):
    client, headers, company_id = company_auth
    payload = {
        "company_id": company_id,
        "activity_type": "email",
        "subject": "Initial outreach",
        "description": "Sent intro email",
    }
    response = await client.post("/api/v1/activities", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["activity_type"] == "email"
    assert data["subject"] == "Initial outreach"


@pytest.mark.asyncio
async def test_list_activities(company_auth):
    client, headers, company_id = company_auth
    await client.post(
        "/api/v1/activities",
        json={"activity_type": "call", "subject": "Discovery call"},
        headers=headers,
    )
    response = await client.get("/api/v1/activities", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["activity_type"] == "call"


@pytest.mark.asyncio
async def test_create_activity_invalid_type(company_auth):
    client, headers, company_id = company_auth
    response = await client.post(
        "/api/v1/activities",
        json={"activity_type": "bogus", "subject": "bad"},
        headers=headers,
    )
    assert response.status_code == 422