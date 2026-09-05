"""Section-17 pipeline metrics: verify each newly-wired counter actually
increments at its real call site (not just that it's registered)."""

import pytest
from httpx import AsyncClient

from app.core.metrics import metrics
from tests.conftest import create_company, register_tenant


@pytest.mark.asyncio
async def test_leads_created_total_increments(client: AsyncClient):
    headers = await register_tenant(client, "metrics-lead", "metrics-lead@example.com")
    company_id = await create_company(client, headers, "m")
    before = metrics.count("leads_created_total")
    resp = await client.post("/api/v1/leads", json={"company_id": company_id}, headers=headers)
    assert resp.status_code == 201
    assert metrics.count("leads_created_total") == before + 1


@pytest.mark.asyncio
async def test_leads_qualified_total_increments_only_on_qualified(client: AsyncClient):
    headers = await register_tenant(client, "metrics-qual", "metrics-qual@example.com")
    company_id = await create_company(client, headers, "m")
    lead = (
        await client.post("/api/v1/leads", json={"company_id": company_id}, headers=headers)
    ).json()
    evidence = (
        await client.post(
            "/api/v1/evidence",
            json={
                "company_id": company_id,
                "source_url": "https://x.example/a",
                "evidence_type": "news",
            },
            headers=headers,
        )
    ).json()

    before = metrics.count("leads_qualified_total")
    resp = await client.post(
        f"/api/v1/leads/{lead['id']}/qualify",
        json={"status": "candidate", "evidence_ids": [evidence["id"]]},
        headers=headers,
    )
    assert resp.status_code == 200
    assert metrics.count("leads_qualified_total") == before  # "candidate" != "qualified"

    resp2 = await client.post(
        f"/api/v1/leads/{lead['id']}/qualify",
        json={"status": "qualified", "evidence_ids": [evidence["id"]]},
        headers=headers,
    )
    assert resp2.status_code == 200
    assert metrics.count("leads_qualified_total") == before + 1


@pytest.mark.asyncio
async def test_signals_detected_total_increments_only_on_new_signal(client: AsyncClient):
    headers = await register_tenant(client, "metrics-sig", "metrics-sig@example.com")
    company_id = await create_company(client, headers, "m")
    evidence = (
        await client.post(
            "/api/v1/evidence",
            json={
                "company_id": company_id,
                "source_url": "https://x.example/careers",
                "evidence_type": "hiring",
            },
            headers=headers,
        )
    ).json()

    before = metrics.count("signals_detected_total")
    first = await client.post(f"/api/v1/evidence/{evidence['id']}/detect-signal", headers=headers)
    assert first.status_code == 200 and first.json() is not None
    assert metrics.count("signals_detected_total") == before + 1

    # Re-running against the same evidence returns the existing signal
    # (idempotent) — must not double-count.
    second = await client.post(f"/api/v1/evidence/{evidence['id']}/detect-signal", headers=headers)
    assert second.json()["id"] == first.json()["id"]
    assert metrics.count("signals_detected_total") == before + 1


@pytest.mark.asyncio
async def test_outreach_policy_denied_total_increments_on_dnc(client: AsyncClient):
    headers = await register_tenant(client, "metrics-denied", "metrics-denied@example.com")
    company_id = await create_company(client, headers, "m")
    contact = (
        await client.post(
            "/api/v1/contacts", json={"company_id": company_id, "email": "a@b.com"}, headers=headers
        )
    ).json()
    await client.post("/api/v1/leads", json={"company_id": company_id}, headers=headers)
    await client.post(
        "/api/v1/do-not-contact",
        json={"contact_id": contact["id"], "channel": "email", "reason": "opt out"},
        headers=headers,
    )
    template = (
        await client.post(
            "/api/v1/templates",
            json={"name": "t", "channel": "email", "body": "hi"},
            headers=headers,
        )
    ).json()

    before = metrics.count("outreach_policy_denied_total")
    resp = await client.post(
        "/api/v1/outreach",
        json={"contact_id": contact["id"], "channel": "email", "template_id": template["id"]},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "denied"
    assert metrics.count("outreach_policy_denied_total") == before + 1


@pytest.mark.asyncio
async def test_outreach_queued_total_increments_on_dispatch(client: AsyncClient):
    headers = await register_tenant(client, "metrics-queued", "metrics-queued@example.com")
    company_id = await create_company(client, headers, "m")
    contact = (
        await client.post(
            "/api/v1/contacts", json={"company_id": company_id, "email": "a@b.com"}, headers=headers
        )
    ).json()
    lead_resp = await client.post("/api/v1/leads", json={"company_id": company_id}, headers=headers)
    lead_id = lead_resp.json()["id"]
    evidence = (
        await client.post(
            "/api/v1/evidence",
            json={
                "company_id": company_id,
                "source_url": "https://x.example/a",
                "evidence_type": "news",
            },
            headers=headers,
        )
    ).json()
    await client.post(
        f"/api/v1/leads/{lead_id}/qualify",
        json={"status": "qualified", "evidence_ids": [evidence["id"]]},
        headers=headers,
    )
    await client.post(f"/api/v1/leads/{lead_id}/score", headers=headers)
    await client.post(
        "/api/v1/consents",
        json={"contact_id": contact["id"], "basis": "consent", "channel": "email"},
        headers=headers,
    )
    template = (
        await client.post(
            "/api/v1/templates",
            json={"name": "t", "channel": "email", "body": "hi"},
            headers=headers,
        )
    ).json()
    outreach = (
        await client.post(
            "/api/v1/outreach",
            json={"contact_id": contact["id"], "channel": "email", "template_id": template["id"]},
            headers=headers,
        )
    ).json()
    assert outreach["status"] == "approved"

    before = metrics.count("outreach_queued_total")
    dispatched = await client.post(
        f"/api/v1/outreach/{outreach['id']}/dispatch", headers=headers
    )
    assert dispatched.status_code == 200
    assert metrics.count("outreach_queued_total") == before + 1


@pytest.mark.asyncio
async def test_discovery_jobs_created_total_increments_once_per_unique_target(
    client: AsyncClient,
):
    headers = await register_tenant(client, "metrics-disc", "metrics-disc@example.com")
    before = metrics.count("discovery_jobs_created_total")
    r1 = await client.post(
        "/api/v1/discovery/jobs", json={"target": "https://metrics-target.example"}, headers=headers
    )
    r2 = await client.post(
        "/api/v1/discovery/jobs", json={"target": "https://metrics-target.example"}, headers=headers
    )
    assert r1.json()["id"] == r2.json()["id"]  # dedup by target_hash
    assert metrics.count("discovery_jobs_created_total") == before + 1
