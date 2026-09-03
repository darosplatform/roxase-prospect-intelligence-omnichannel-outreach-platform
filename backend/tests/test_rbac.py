import pytest
from httpx import AsyncClient

from tests.conftest import create_company, create_user_with_role, register_tenant


async def _owner_and_viewer(client, suffix):
    owner_headers = await register_tenant(client, f"rbac-{suffix}", f"rbac{suffix}@example.com")
    viewer_headers = await create_user_with_role(
        client, owner_headers, f"viewer{suffix}@example.com", "viewer"
    )
    company_id = await create_company(client, owner_headers, suffix)
    return owner_headers, viewer_headers, company_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint,payload",
    [
        ("/api/v1/signals", {"signal_type": "funding"}),
        ("/api/v1/opportunities", {"name": "Deal"}),
        ("/api/v1/tasks", {"title": "Task"}),
        ("/api/v1/campaigns", {"name": "Camp"}),
        ("/api/v1/notes", {"content": "Note"}),
    ],
)
async def test_viewer_cannot_create(client: AsyncClient, endpoint, payload):
    _, viewer_headers, company_id = await _owner_and_viewer(client, "create")
    body = dict(payload)
    if endpoint in ("/api/v1/signals", "/api/v1/opportunities"):
        body["company_id"] = company_id

    resp = await client.post(endpoint, json=body, headers=viewer_headers)
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_viewer_cannot_create_activity(client: AsyncClient):
    _, viewer_headers, _ = await _owner_and_viewer(client, "act")
    resp = await client.post(
        "/api/v1/activities",
        json={"activity_type": "email", "subject": "x"},
        headers=viewer_headers,
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_owner_can_create_opportunity(client: AsyncClient):
    owner_headers, _, company_id = await _owner_and_viewer(client, "owncreate")
    resp = await client.post(
        "/api/v1/opportunities",
        json={"company_id": company_id, "name": "Owner Deal"},
        headers=owner_headers,
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_viewer_cannot_patch_campaign(client: AsyncClient):
    owner_headers, viewer_headers, _ = await _owner_and_viewer(client, "patchcamp")
    create_resp = await client.post(
        "/api/v1/campaigns", json={"name": "Camp"}, headers=owner_headers
    )
    campaign_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/campaigns/{campaign_id}",
        json={"status": "running"},
        headers=viewer_headers,
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_viewer_cannot_delete_task(client: AsyncClient):
    owner_headers, viewer_headers, _ = await _owner_and_viewer(client, "deltask")
    create_resp = await client.post("/api/v1/tasks", json={"title": "T"}, headers=owner_headers)
    task_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/v1/tasks/{task_id}", headers=viewer_headers)
    assert resp.status_code == 403, resp.text