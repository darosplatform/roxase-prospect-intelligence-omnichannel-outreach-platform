import pytest
from httpx import AsyncClient

from tests.conftest import create_company, register_tenant

# Resources that expose GET /<resource>/{id}
GET_RESOURCES = ["opportunities", "campaigns"]
# Resources that expose PATCH /<resource>/{id} (read-modify probe by id)
PATCH_RESOURCES = ["tasks", "campaigns"]


async def _create_resource_owned_by_tenant(client, headers_b, kind):
    company_b = await create_company(client, headers_b, kind)
    if kind == "signals":
        resp = await client.post(
            "/api/v1/signals",
            json={"company_id": company_b, "signal_type": "funding"},
            headers=headers_b,
        )
    elif kind == "opportunities":
        resp = await client.post(
            "/api/v1/opportunities",
            json={"company_id": company_b, "name": f"Deal-{kind}"},
            headers=headers_b,
        )
    elif kind == "notes":
        resp = await client.post(
            "/api/v1/notes", json={"company_id": company_b, "content": "secret"}, headers=headers_b
        )
    elif kind == "tasks":
        resp = await client.post(
            "/api/v1/tasks", json={"company_id": company_b, "title": "Sec"}, headers=headers_b
        )
    elif kind == "campaigns":
        resp = await client.post(
            "/api/v1/campaigns", json={"name": "Camp", "channel": "email"}, headers=headers_b
        )
    else:
        pytest.fail(f"no creator for {kind}")
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_listing_is_tenant_scoped(company_auth, client: AsyncClient):
    client, headers_a, _ = company_auth
    headers_b = await register_tenant(client, "tenant-sec-list", "seclist@example.com")
    await _create_resource_owned_by_tenant(client, headers_b, "signals")

    list_resp = await client.get("/api/v1/signals", headers=headers_a)
    assert list_resp.status_code == 200
    assert list_resp.json() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", GET_RESOURCES)
async def test_cross_tenant_get_returns_404(company_auth, client: AsyncClient, kind):
    client, headers_a, _ = company_auth
    headers_b = await register_tenant(client, f"tenant-sec-get-{kind}", f"secget{kind}@example.com")
    resource_id = await _create_resource_owned_by_tenant(client, headers_b, kind)

    get_resp = await client.get(f"/api/v1/{kind}/{resource_id}", headers=headers_a)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", PATCH_RESOURCES)
async def test_cross_tenant_patch_returns_404(company_auth, client: AsyncClient, kind):
    client, headers_a, _ = company_auth
    headers_b = await register_tenant(
        client, f"tenant-sec-patch-{kind}", f"secpatch{kind}@example.com"
    )
    resource_id = await _create_resource_owned_by_tenant(client, headers_b, kind)

    if kind == "tasks":
        path = f"/api/v1/tasks/{resource_id}"
        payload = {"status": "done"}
    else:
        path = f"/api/v1/campaigns/{resource_id}"
        payload = {"status": "running"}

    patch_resp = await client.patch(path, json=payload, headers=headers_a)
    assert patch_resp.status_code == 404