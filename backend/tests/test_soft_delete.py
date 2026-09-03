import pytest
from httpx import AsyncClient

from tests.conftest import create_company, register_tenant


async def _setup(client, suffix):
    headers = await register_tenant(client, f"soft-{suffix}", f"soft{suffix}@example.com")
    company_id = await create_company(client, headers, suffix)
    return headers, company_id


@pytest.mark.asyncio
async def test_signal_soft_delete_hides_from_list(client: AsyncClient):
    headers, company_id = await _setup(client, "signal")
    create_resp = await client.post(
        "/api/v1/signals",
        json={"company_id": company_id, "signal_type": "funding"},
        headers=headers,
    )
    signal_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/signals/{signal_id}", headers=headers)
    assert del_resp.status_code == 204

    list_resp = await client.get("/api/v1/signals", headers=headers)
    assert list_resp.json() == []

    get_resp = await client.get(f"/api/v1/signals/{signal_id}", headers=headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_task_soft_delete_hides_from_list(client: AsyncClient):
    headers, _ = await _setup(client, "task")
    create_resp = await client.post("/api/v1/tasks", json={"title": "T"}, headers=headers)
    task_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/tasks/{task_id}", headers=headers)
    assert del_resp.status_code == 204

    list_resp = await client.get("/api/v1/tasks", headers=headers)
    assert list_resp.json() == []

    patch_resp = await client.patch(
        f"/api/v1/tasks/{task_id}", json={"status": "done"}, headers=headers
    )
    assert patch_resp.status_code == 404


@pytest.mark.asyncio
async def test_campaign_soft_delete_hides_from_get(client: AsyncClient):
    headers, _ = await _setup(client, "campaign")
    create_resp = await client.post("/api/v1/campaigns", json={"name": "C"}, headers=headers)
    campaign_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/campaigns/{campaign_id}", headers=headers)
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/campaigns/{campaign_id}", headers=headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_opportunity_soft_delete_hides_from_list(client: AsyncClient):
    headers, company_id = await _setup(client, "opp")
    create_resp = await client.post(
        "/api/v1/opportunities",
        json={"company_id": company_id, "name": "D"},
        headers=headers,
    )
    opp_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/opportunities/{opp_id}", headers=headers)
    assert del_resp.status_code == 204

    list_resp = await client.get("/api/v1/opportunities", headers=headers)
    assert list_resp.json() == []


@pytest.mark.asyncio
async def test_note_soft_delete_hides_from_list(client: AsyncClient):
    headers, _ = await _setup(client, "note")
    create_resp = await client.post("/api/v1/notes", json={"content": "N"}, headers=headers)
    note_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/notes/{note_id}", headers=headers)
    assert del_resp.status_code == 204

    list_resp = await client.get("/api/v1/notes", headers=headers)
    assert list_resp.json() == []