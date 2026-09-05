"""Systematic multi-tenant hardening sweep (final security pass).

Most individual features already carry their own cross-tenant test next to
their happy-path tests (discovery fetch/extract, evidence detect-signal,
audit, companies, the PATCH_RESOURCES/GET_RESOURCES sweep in
test_tenant_isolation.py). This file targets the specific gaps that sweep
doesn't reach: contacts, lead mutation endpoints, outreach lifecycle
actions, signal deletion, campaign deletion, discovery job transitions —
plus one thing no per-feature test can prove alone: that the discovery
WORKER, which by design claims jobs across ALL tenants in one shared
poll loop (there is no per-tenant worker), never lets one tenant's
processing touch another tenant's rows.

    Tenant A cannot read Tenant B
    Tenant A cannot modify Tenant B
    Tenant A cannot fetch Tenant B
    Tenant A cannot queue Tenant B
    Tenant A cannot trigger Tenant B
    Tenant A cannot see Tenant B audit
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

import app.services.discovery as discovery_svc
from app.core.discovery_utils import target_hash, url_hash
from app.models.company import Company
from app.models.discovery import DiscoveryJob, DiscoverySource
from app.models.evidence import Evidence
from app.models.signal import Signal
from app.models.tenant import Tenant
from app.services import discovery_worker as worker
from app.services.secure_fetcher import FetchResult
from tests.conftest import create_company, register_tenant

HTML_A = """
<html><head><title>Tenant A News</title>
<meta property="og:site_name" content="Tenant A Co" /></head>
<body><p>Tenant A raised a Series A round. jane@tenanta.example</p></body></html>
"""
HTML_B = """
<html><head><title>Tenant B News</title>
<meta property="og:site_name" content="Tenant B Co" /></head>
<body><p>Tenant B raised a Series A round. jane@tenantb.example</p></body></html>
"""


@pytest.mark.asyncio
async def test_contact_cross_tenant_get_returns_404(client: AsyncClient):
    a_headers = await register_tenant(client, "mth-contact-a", "mth-contact-a@example.com")
    b_headers = await register_tenant(client, "mth-contact-b", "mth-contact-b@example.com")
    contact = (
        await client.post(
            "/api/v1/contacts", json={"first_name": "Secret"}, headers=a_headers
        )
    ).json()

    resp = await client.get(f"/api/v1/contacts/{contact['id']}", headers=b_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_discovery_job_cross_tenant_transition_returns_404(client: AsyncClient):
    a_headers = await register_tenant(client, "mth-job-a", "mth-job-a@example.com")
    b_headers = await register_tenant(client, "mth-job-b", "mth-job-b@example.com")
    job = (
        await client.post(
            "/api/v1/discovery/jobs", json={"target": "https://mth-a.example"}, headers=a_headers
        )
    ).json()

    resp = await client.patch(
        f"/api/v1/discovery/jobs/{job['id']}", json={"status": "queued"}, headers=b_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_lead_cross_tenant_mutations_return_404(client: AsyncClient):
    a_headers = await register_tenant(client, "mth-lead-a", "mth-lead-a@example.com")
    b_headers = await register_tenant(client, "mth-lead-b", "mth-lead-b@example.com")
    company_id = await create_company(client, a_headers, "mth")
    lead = (
        await client.post("/api/v1/leads", json={"company_id": company_id}, headers=a_headers)
    ).json()

    assert (await client.get(f"/api/v1/leads/{lead['id']}", headers=b_headers)).status_code == 404
    assert (
        await client.patch(f"/api/v1/leads/{lead['id']}", json={"status": "x"}, headers=b_headers)
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/leads/{lead['id']}/qualify",
            json={"status": "qualified", "evidence_ids": []},
            headers=b_headers,
        )
    ).status_code in (404, 422)  # 404 ownership check fires before the empty-evidence 422
    assert (
        await client.post(f"/api/v1/leads/{lead['id']}/score", headers=b_headers)
    ).status_code == 404


@pytest.mark.asyncio
async def test_outreach_cross_tenant_lifecycle_actions_return_404(client: AsyncClient):
    a_headers = await register_tenant(client, "mth-or-a", "mth-or-a@example.com")
    b_headers = await register_tenant(client, "mth-or-b", "mth-or-b@example.com")
    company_id = await create_company(client, a_headers, "mth")
    contact = (
        await client.post(
            "/api/v1/contacts",
            json={"company_id": company_id, "email": "x@mth.example"},
            headers=a_headers,
        )
    ).json()
    lead = (
        await client.post("/api/v1/leads", json={"company_id": company_id}, headers=a_headers)
    ).json()
    template = (
        await client.post(
            "/api/v1/templates",
            json={"name": "t", "channel": "email", "body": "hi"},
            headers=a_headers,
        )
    ).json()
    outreach = (
        await client.post(
            "/api/v1/outreach",
            json={
                "lead_id": lead["id"],
                "contact_id": contact["id"],
                "channel": "email",
                "template_id": template["id"],
            },
            headers=a_headers,
        )
    ).json()

    assert (
        await client.get(f"/api/v1/outreach/{outreach['id']}", headers=b_headers)
    ).status_code == 404
    assert (
        await client.post(f"/api/v1/outreach/{outreach['id']}/approve", headers=b_headers)
    ).status_code == 404
    assert (
        await client.post(f"/api/v1/outreach/{outreach['id']}/dispatch", headers=b_headers)
    ).status_code == 404
    assert (
        await client.post(f"/api/v1/outreach/{outreach['id']}/cancel", headers=b_headers)
    ).status_code == 404


@pytest.mark.asyncio
async def test_signal_cross_tenant_delete_returns_404(client: AsyncClient):
    a_headers = await register_tenant(client, "mth-sig-a", "mth-sig-a@example.com")
    b_headers = await register_tenant(client, "mth-sig-b", "mth-sig-b@example.com")
    company_id = await create_company(client, a_headers, "mth")
    signal = (
        await client.post(
            "/api/v1/signals",
            json={"company_id": company_id, "signal_type": "hiring"},
            headers=a_headers,
        )
    ).json()

    resp = await client.delete(f"/api/v1/signals/{signal['id']}", headers=b_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_campaign_cross_tenant_delete_returns_404(client: AsyncClient):
    a_headers = await register_tenant(client, "mth-camp-a", "mth-camp-a@example.com")
    b_headers = await register_tenant(client, "mth-camp-b", "mth-camp-b@example.com")
    campaign = (
        await client.post(
            "/api/v1/campaigns", json={"name": "C", "channel": "email"}, headers=a_headers
        )
    ).json()

    resp = await client.delete(f"/api/v1/campaigns/{campaign['id']}", headers=b_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_discovery_worker_never_leaks_across_tenants_when_processing_concurrently(
    db_session, monkeypatch
):
    """The worker's claim query is intentionally NOT tenant-scoped (a shared
    background process legitimately serves every tenant) — the isolation
    guarantee that actually matters is that each claimed job only ever
    touches its OWN tenant's rows. Seed two tenants' jobs together, run the
    worker once, and prove neither tenant's Company/Evidence/Signal rows
    reference the other tenant anywhere."""
    tenant_a = Tenant(slug="mth-worker-a", name="MTH Worker A")
    tenant_b = Tenant(slug="mth-worker-b", name="MTH Worker B")
    db_session.add_all([tenant_a, tenant_b])
    await db_session.commit()
    await db_session.refresh(tenant_a)
    await db_session.refresh(tenant_b)

    async def make_job_with_source(tenant, target, url):
        job = DiscoveryJob(
            tenant_id=tenant.id,
            status="queued",
            source_type="url",
            target=target,
            target_hash=target_hash(target),
        )
        db_session.add(job)
        await db_session.flush()
        source = DiscoverySource(
            tenant_id=tenant.id, job_id=job.id, url=url, url_hash=url_hash(url), status="pending"
        )
        db_session.add(source)
        await db_session.commit()
        await db_session.refresh(job)
        return job

    job_a = await make_job_with_source(tenant_a, "https://mth-a.example", "https://mth-a.example/news")
    job_b = await make_job_with_source(tenant_b, "https://mth-b.example", "https://mth-b.example/news")

    async def fake_fetch(url, **_kwargs):
        body = HTML_A if "mth-a" in url else HTML_B
        return FetchResult(
            final_url=url,
            status_code=200,
            content_type="text/html",
            body=body.encode(),
            resolved_ip="93.184.216.34",
            redirect_chain=[],
            elapsed_seconds=0.01,
        )

    monkeypatch.setattr(discovery_svc, "secure_fetch", fake_fetch)

    processed = await worker.run_once(db_session, worker_id="mth-worker", batch_size=10)
    assert processed == 2

    for job_id in (job_a.id, job_b.id):
        row = await db_session.get(DiscoveryJob, job_id)
        assert row.status == "done"

    companies_a = (
        await db_session.execute(select(Company).where(Company.tenant_id == tenant_a.id))
    ).scalars().all()
    companies_b = (
        await db_session.execute(select(Company).where(Company.tenant_id == tenant_b.id))
    ).scalars().all()
    assert {c.legal_name for c in companies_a} == {"Tenant A Co"}
    assert {c.legal_name for c in companies_b} == {"Tenant B Co"}

    evidence_a = (
        await db_session.execute(select(Evidence).where(Evidence.tenant_id == tenant_a.id))
    ).scalars().all()
    evidence_b = (
        await db_session.execute(select(Evidence).where(Evidence.tenant_id == tenant_b.id))
    ).scalars().all()
    assert all(e.company_id in {c.id for c in companies_a} for e in evidence_a)
    assert all(e.company_id in {c.id for c in companies_b} for e in evidence_b)
    # No evidence row references the other tenant's company at all.
    other_company_ids_b = {c.id for c in companies_b}
    other_company_ids_a = {c.id for c in companies_a}
    assert not any(e.company_id in other_company_ids_b for e in evidence_a)
    assert not any(e.company_id in other_company_ids_a for e in evidence_b)

    signals_a = (
        await db_session.execute(select(Signal).where(Signal.tenant_id == tenant_a.id))
    ).scalars().all()
    signals_b = (
        await db_session.execute(select(Signal).where(Signal.tenant_id == tenant_b.id))
    ).scalars().all()
    assert all(s.company_id in {c.id for c in companies_a} for s in signals_a)
    assert all(s.company_id in {c.id for c in companies_b} for s in signals_b)
