import pytest
from httpx import AsyncClient

from tests.conftest import create_user_with_role, register_tenant, tenant_id_from_token


@pytest.mark.asyncio
async def test_register_creates_tenant_user_and_tokens(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        params={"slug": "acme"},
        json={
            "email": "ceo@acme.com",
            "password": "supersecret",
            "full_name": "Acme CEO",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_rejects_duplicate_slug(client: AsyncClient):
    payload = {
        "email": "a@example.com",
        "password": "supersecret",
        "full_name": "User A",
    }
    first = await client.post("/api/v1/auth/register", params={"slug": "dup"}, json=payload)
    assert first.status_code == 201

    second = await client.post(
        "/api/v1/auth/register",
        params={"slug": "dup"},
        json={"email": "b@example.com", "password": "supersecret"},
    )
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        params={"slug": "loginco"},
        json={"email": "admin@loginco.com", "password": "supersecret"},
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@loginco.com", "password": "supersecret"},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_login_rejects_wrong_password(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        params={"slug": "loginfail"},
        json={"email": "x@loginfail.com", "password": "supersecret"},
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "x@loginfail.com", "password": "wrongpass"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/companies")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_user_in_tenant_requires_auth(client: AsyncClient):
    """POST /auth/users used to accept an arbitrary tenant_id with no auth at
    all -- anyone could mint an owner account in any tenant. It must now
    require a Bearer token."""
    response = await client.post(
        "/api/v1/auth/users",
        params={"email": "intruder@example.com", "password": "supersecret", "role": "owner"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_user_in_tenant_rejects_low_privilege_caller(client: AsyncClient):
    owner_headers = await register_tenant(client, "authz-tenant", "owner@authz.example")
    viewer_headers = await create_user_with_role(
        client, owner_headers, "viewer@authz.example", "viewer"
    )
    response = await client.post(
        "/api/v1/auth/users",
        params={"email": "escalated@authz.example", "password": "supersecret", "role": "owner"},
        headers=viewer_headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_user_in_tenant_ignores_client_supplied_tenant_id(client: AsyncClient):
    """Even if a caller (legitimately an owner/admin of their own tenant)
    passes a foreign tenant_id, the new user must land in the caller's own
    tenant -- never the tenant named in the request."""
    own_headers = await register_tenant(client, "authz-own", "owner@authz-own.example")
    other_headers = await register_tenant(client, "authz-other", "owner@authz-other.example")
    other_tenant_id = tenant_id_from_token(other_headers["Authorization"].split(" ")[1])

    response = await client.post(
        "/api/v1/auth/users",
        params={
            "tenant_id": other_tenant_id,
            "email": "scoped@authz-own.example",
            "password": "supersecret",
            "role": "manager",
        },
        headers=own_headers,
    )
    assert response.status_code == 201, response.text
    new_user_tenant_id = tenant_id_from_token(response.json()["access_token"])
    own_tenant_id = tenant_id_from_token(own_headers["Authorization"].split(" ")[1])
    assert new_user_tenant_id == own_tenant_id
    assert new_user_tenant_id != other_tenant_id