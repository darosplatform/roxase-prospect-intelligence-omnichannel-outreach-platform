import pytest


@pytest.mark.asyncio
async def test_create_campaign(company_auth):
    client, headers, _ = company_auth
    payload = {
        "name": "Q3 Outbound",
        "description": "Cold email campaign",
        "status": "draft",
        "channel": "email",
    }
    response = await client.post("/api/v1/campaigns", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Q3 Outbound"
    assert data["status"] == "draft"
    assert data["channel"] == "email"
    assert data["created_by"] is not None


@pytest.mark.asyncio
async def test_list_get_campaign(company_auth):
    client, headers, _ = company_auth
    create_resp = await client.post(
        "/api/v1/campaigns",
        json={"name": "Campaign", "channel": "whatsapp"},
        headers=headers,
    )
    campaign_id = create_resp.json()["id"]

    list_resp = await client.get("/api/v1/campaigns", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    get_resp = await client.get(f"/api/v1/campaigns/{campaign_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["channel"] == "whatsapp"


@pytest.mark.asyncio
async def test_update_campaign(company_auth):
    client, headers, _ = company_auth
    create_resp = await client.post(
        "/api/v1/campaigns",
        json={"name": "Campaign", "status": "draft"},
        headers=headers,
    )
    campaign_id = create_resp.json()["id"]

    patch = await client.patch(
        f"/api/v1/campaigns/{campaign_id}",
        json={"status": "running"},
        headers=headers,
    )
    assert patch.status_code == 200
    assert patch.json()["status"] == "running"


@pytest.mark.asyncio
async def test_create_campaign_invalid_channel(company_auth):
    client, headers, _ = company_auth
    response = await client.post(
        "/api/v1/campaigns",
        json={"name": "Bad", "channel": "carrier_pigeon"},
        headers=headers,
    )
    assert response.status_code == 422