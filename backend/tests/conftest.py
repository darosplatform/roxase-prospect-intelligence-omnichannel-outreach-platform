from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app

TEST_DATABASE_URL = "postgresql+asyncpg://roxase:roxase@localhost:5433/roxase_test"


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(test_engine) -> AsyncGenerator[AsyncClient, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        params={"slug": "tenant-a"},
        json={
            "email": "owner@example.com",
            "password": "supersecret",
            "full_name": "Owner User",
        },
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return client, headers


async def register_tenant(client: AsyncClient, slug: str, email: str):
    response = await client.post(
        "/api/v1/auth/register",
        params={"slug": slug},
        json={"email": email, "password": "supersecret"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def create_company(client: AsyncClient, headers: dict, suffix: str = ""):
    response = await client.post(
        "/api/v1/companies",
        json={"legal_name": f"Company{suffix}", "domain": f"company{suffix}.com"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest_asyncio.fixture
async def company_auth(client: AsyncClient):
    headers = await register_tenant(client, "tenant-crm", "crm@example.com")
    company_id = await create_company(client, headers, "CRM")
    return client, headers, company_id


async def create_contact(client: AsyncClient, headers: dict, suffix: str = ""):
    response = await client.post(
        "/api/v1/contacts",
        json={"first_name": f"Contact{suffix}", "last_name": f"Last{suffix}"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def create_lead(client: AsyncClient, headers: dict, suffix: str = ""):
    response = await client.post(
        "/api/v1/leads",
        json={"status": "new"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def tenant_id_from_token(token: str):
    from app.core.security import decode_token

    payload = decode_token(token)
    assert payload is not None
    return payload["tenant_id"]


async def create_user_with_role(
    client: AsyncClient, owner_headers: dict, email: str, role: str
):
    tenant_id = tenant_id_from_token(owner_headers["Authorization"].split(" ")[1])
    response = await client.post(
        "/api/v1/auth/users",
        params={
            "tenant_id": tenant_id,
            "email": email,
            "password": "supersecret",
            "role": role,
        },
        json=None,
        headers=owner_headers,
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}