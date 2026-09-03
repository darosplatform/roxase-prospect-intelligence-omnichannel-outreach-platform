import pytest
from httpx import AsyncClient


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