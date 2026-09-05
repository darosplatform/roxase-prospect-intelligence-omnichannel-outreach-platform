from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
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


@pytest_asyncio.fixture(autouse=True)
async def _reset_rate_limits():
    """Every test shares one rate-limited "identity" (the ASGI test client
    reports a constant host, and unauthenticated routes like /auth/register
    fall back to it), so fixed-window counters in Redis accumulate across
    unrelated tests. Left alone, a fast, growing test suite eventually trips
    a real 429 on an ordinary test with no bursty behavior of its own — a
    flaky-suite bug, not an application bug (the limiter itself is correct).
    Clearing only the rate-limit keys (not all of Redis, though nothing else
    currently lives there) before each test keeps the suite deterministic.

    Deliberately does NOT use app.core.cache.get_redis() to clear those keys:
    that client is a process-global singleton bound to whichever event loop
    first created it, which under pytest-asyncio's per-test event loop
    breaks on any later test with "Event loop is closed" (the default-scope
    RateLimiter never hit this because it silently swallows that exact
    exception and degrades open -- but a fail-closed limiter, e.g. on the
    auth endpoints, surfaces it as a real, suite-wide 503). A short-lived
    connection scoped to this fixture's own loop avoids the cross-loop reuse
    for the cleanup itself.

    Also resets app.core.cache.redis_client to None so that the *app's own*
    next real get_redis() call (inside RateLimiter, triggered by whatever
    this test does) lazily builds a fresh client bound to this test's event
    loop, instead of reusing a connection left over from a previous test's
    now-closed loop. Tests in test_hardening.py that monkeypatch
    app.core.cache.redis_client themselves run after this fixture, so their
    explicit fake client is unaffected.
    """
    from redis.asyncio import Redis

    import app.core.cache as cache

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        async for key in redis.scan_iter("rl:*"):
            await redis.delete(key)
    finally:
        await redis.aclose()
    cache.redis_client = None
    yield


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


async def create_evidence(
    client: AsyncClient, headers: dict, suffix: str = "", company_id: str | None = None
):
    body = {
        "source_url": f"https://ev{suffix}.com/r",
        "source_name": f"Source{suffix}",
        "evidence_type": "news",
        "title": f"Evidence {suffix}",
    }
    if company_id:
        body["company_id"] = company_id
    response = await client.post("/api/v1/evidence", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def create_signal(
    client: AsyncClient,
    headers: dict,
    company_id: str,
    signal_type: str = "hiring",
    evidence_id: str | None = None,
    confidence: float = 1.0,
    detected_at: str | None = None,
    status: str = "new",
):
    body = {"company_id": company_id, "signal_type": signal_type, "confidence": confidence}
    if evidence_id:
        body["evidence_id"] = evidence_id
    if detected_at:
        body["detected_at"] = detected_at
    if status:
        body["status"] = status
    response = await client.post("/api/v1/signals", json=body, headers=headers)
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