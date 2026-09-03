import pytest
from httpx import AsyncClient

from tests.conftest import create_company, register_tenant


async def _setup(client, suffix):
    headers = await register_tenant(client, f"val-{suffix}", f"val{suffix}@example.com")
    company_id = await create_company(client, headers, suffix)
    return headers, company_id


@pytest.mark.asyncio
async def test_signal_dedup_returns_409(client: AsyncClient):
    headers, company_id = await _setup(client, "dedup")
    payload = {
        "company_id": company_id,
        "signal_type": "funding",
        "source_url": "https://example.com/a",
    }
    first = await client.post("/api/v1/signals", json=payload, headers=headers)
    assert first.status_code == 201

    second = await client.post("/api/v1/signals", json=payload, headers=headers)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_signal_rejects_invalid_status(client: AsyncClient):
    headers, company_id = await _setup(client, "status")
    resp = await client.post(
        "/api/v1/signals",
        json={"company_id": company_id, "signal_type": "funding", "status": "bogus"},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_signal_rejects_negative_confidence(client: AsyncClient):
    headers, company_id = await _setup(client, "confneg")
    resp = await client.post(
        "/api/v1/signals",
        json={"company_id": company_id, "signal_type": "funding", "confidence": -0.1},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_opportunity_rejects_probability_out_of_range(client: AsyncClient):
    headers, company_id = await _setup(client, "prob")
    resp = await client.post(
        "/api/v1/opportunities",
        json={"company_id": company_id, "name": "D", "probability": 1.5},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_opportunity_rejects_invalid_currency(client: AsyncClient):
    headers, company_id = await _setup(client, "curr")
    resp = await client.post(
        "/api/v1/opportunities",
        json={"company_id": company_id, "name": "D", "currency": "eur"},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_opportunity_rejects_invalid_uuid_reference(client: AsyncClient):
    headers, _ = await _setup(client, "uuid")
    resp = await client.post(
        "/api/v1/opportunities",
        json={"company_id": "not-a-uuid", "name": "D"},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_task_rejects_invalid_priority(client: AsyncClient):
    headers, _ = await _setup(client, "prio")
    resp = await client.post(
        "/api/v1/tasks",
        json={"title": "T", "priority": "critical"},
        headers=headers,
    )
    assert resp.status_code == 422