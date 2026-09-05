"""C3 integration: POST /discovery/sources/{id}/extract end to end against
the real API + DB. The network layer is a fake secure_fetch (C2 already has
its own exhaustive test suite); this file focuses on extraction, dedup,
provenance and the C1-C3 boundary.
"""

import pytest
from httpx import AsyncClient

import app.services.discovery as discovery_svc
from app.services.secure_fetcher import FetchResult
from tests.conftest import create_user_with_role, register_tenant

JOB_URL = "/api/v1/discovery/jobs"

HTML_PAGE = """
<html>
<head>
  <title>About Acme Robotics</title>
  <meta property="og:site_name" content="Acme Robotics" />
</head>
<body>
  <h1>Leadership</h1>
  <p>Jane Doe, Chief Executive Officer — <a href="mailto:jane@acme.com">jane@acme.com</a></p>
</body>
</html>
"""

HTML_PAGE_NO_OG = """
<html><head><title>Some Page</title></head>
<body><p>Reach info@acme.com for questions.</p></body></html>
"""


async def _setup_fetched_source(client, headers, url="https://acme.com/leadership", html=HTML_PAGE):
    job_resp = await client.post(JOB_URL, json={"target": "https://acme.com"}, headers=headers)
    assert job_resp.status_code == 201, job_resp.text
    job = job_resp.json()
    src_resp = await client.post(
        f"{JOB_URL}/{job['id']}/sources", json=[{"url": url}], headers=headers
    )
    assert src_resp.status_code == 201, src_resp.text
    source = src_resp.json()[0]
    return job, source


def _fake_fetch(body: bytes, content_type: str = "text/html"):
    async def _fetch(url, **_kwargs):
        return FetchResult(
            final_url=url,
            status_code=200,
            content_type=content_type,
            body=body,
            resolved_ip="93.184.216.34",
            redirect_chain=[],
            elapsed_seconds=0.01,
        )

    return _fetch


@pytest.mark.asyncio
async def test_extract_requires_a_fetched_raw_document(client: AsyncClient):
    headers = await register_tenant(client, "c3-nofetch", "c3-nofetch@example.com")
    _job, source = await _setup_fetched_source(client, headers)
    resp = await client.post(f"/api/v1/discovery/sources/{source['id']}/extract", headers=headers)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_extract_creates_company_contact_and_evidence(
    client: AsyncClient, monkeypatch
):
    headers = await register_tenant(client, "c3-ok", "c3-ok@example.com")
    _job, source = await _setup_fetched_source(client, headers)

    monkeypatch.setattr(discovery_svc, "secure_fetch", _fake_fetch(HTML_PAGE.encode()))
    fetch_resp = await client.post(
        f"/api/v1/discovery/sources/{source['id']}/fetch", headers=headers
    )
    assert fetch_resp.status_code == 200, fetch_resp.text

    resp = await client.post(f"/api/v1/discovery/sources/{source['id']}/extract", headers=headers)
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["page_type"] == "leadership"
    assert result["company_id"]
    assert result["evidence_id"]
    assert len(result["contact_ids"]) == 1

    company_resp = await client.get(f"/api/v1/companies/{result['company_id']}", headers=headers)
    assert company_resp.status_code == 200
    company = company_resp.json()
    assert company["legal_name"] == "Acme Robotics"
    assert company["domain"] == "acme.com"
    assert company["source"] == "discovery"

    contact_resp = await client.get(
        f"/api/v1/contacts/{result['contact_ids'][0]}", headers=headers
    )
    assert contact_resp.status_code == 200
    contact = contact_resp.json()
    assert contact["email"] == "jane@acme.com"
    assert contact["job_title"] == "Chief Executive Officer"
    assert contact["company_id"] == result["company_id"]

    evidence_resp = await client.get("/api/v1/evidence", headers=headers)
    assert evidence_resp.status_code == 200
    evidence_list = evidence_resp.json()
    assert len(evidence_list) == 1
    evidence = evidence_list[0]
    assert evidence["id"] == result["evidence_id"]
    assert evidence["evidence_type"] == "leadership"
    assert evidence["company_id"] == result["company_id"]
    assert evidence["source_url"] == source["url"]
    assert evidence["confidence"] == 0.9  # og:site_name present -> higher confidence
    # Full provenance chain preserved: RawDocument -> DiscoverySource -> DiscoveryJob.
    meta = evidence["metadata"]
    assert meta["discovery_source_id"] == source["id"]
    assert meta["discovery_job_id"] == _job["id"]
    assert meta["raw_document_id"]


@pytest.mark.asyncio
async def test_extract_lower_confidence_without_structured_signal(
    client: AsyncClient, monkeypatch
):
    headers = await register_tenant(client, "c3-noog", "c3-noog@example.com")
    _job, source = await _setup_fetched_source(client, headers, url="https://acme.com/x")

    monkeypatch.setattr(discovery_svc, "secure_fetch", _fake_fetch(HTML_PAGE_NO_OG.encode()))
    await client.post(f"/api/v1/discovery/sources/{source['id']}/fetch", headers=headers)
    resp = await client.post(f"/api/v1/discovery/sources/{source['id']}/extract", headers=headers)
    assert resp.status_code == 200, resp.text

    evidence_resp = await client.get("/api/v1/evidence", headers=headers)
    assert evidence_resp.json()[0]["confidence"] == 0.7


@pytest.mark.asyncio
async def test_extract_is_idempotent_on_repeat_run(client: AsyncClient, monkeypatch):
    headers = await register_tenant(client, "c3-idem", "c3-idem@example.com")
    _job, source = await _setup_fetched_source(client, headers)

    monkeypatch.setattr(discovery_svc, "secure_fetch", _fake_fetch(HTML_PAGE.encode()))
    await client.post(f"/api/v1/discovery/sources/{source['id']}/fetch", headers=headers)
    first = await client.post(
        f"/api/v1/discovery/sources/{source['id']}/extract", headers=headers
    )
    second = await client.post(
        f"/api/v1/discovery/sources/{source['id']}/extract", headers=headers
    )
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["company_id"] == second.json()["company_id"]
    assert first.json()["contact_ids"] == second.json()["contact_ids"]

    companies = await client.get("/api/v1/companies", headers=headers)
    contacts = await client.get("/api/v1/contacts", headers=headers)
    assert len(companies.json()) == 1
    assert len(contacts.json()) == 1


@pytest.mark.asyncio
async def test_extract_never_creates_signal_or_lead(client: AsyncClient, monkeypatch):
    headers = await register_tenant(client, "c3-boundary", "c3-boundary@example.com")
    _job, source = await _setup_fetched_source(client, headers)

    monkeypatch.setattr(discovery_svc, "secure_fetch", _fake_fetch(HTML_PAGE.encode()))
    await client.post(f"/api/v1/discovery/sources/{source['id']}/fetch", headers=headers)
    await client.post(f"/api/v1/discovery/sources/{source['id']}/extract", headers=headers)

    signals = await client.get("/api/v1/signals", headers=headers)
    leads = await client.get("/api/v1/leads", headers=headers)
    assert signals.json() == []
    assert leads.json() == []


@pytest.mark.asyncio
async def test_extract_unsupported_content_type_skips_gracefully(
    client: AsyncClient, monkeypatch
):
    headers = await register_tenant(client, "c3-badct", "c3-badct@example.com")
    _job, source = await _setup_fetched_source(client, headers)

    monkeypatch.setattr(
        discovery_svc, "secure_fetch", _fake_fetch(b"binary", content_type="application/zip")
    )
    await client.post(f"/api/v1/discovery/sources/{source['id']}/fetch", headers=headers)
    resp = await client.post(f"/api/v1/discovery/sources/{source['id']}/extract", headers=headers)
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["skipped_reason"] == "unsupported_content_type"
    assert result["company_id"] is None
    assert result["evidence_id"] is None


@pytest.mark.asyncio
async def test_extract_cross_tenant_returns_404(client: AsyncClient, monkeypatch):
    a_headers = await register_tenant(client, "c3-iso-a", "c3-iso-a@example.com")
    b_headers = await register_tenant(client, "c3-iso-b", "c3-iso-b@example.com")
    _job, source = await _setup_fetched_source(client, a_headers)

    monkeypatch.setattr(discovery_svc, "secure_fetch", _fake_fetch(HTML_PAGE.encode()))
    await client.post(f"/api/v1/discovery/sources/{source['id']}/fetch", headers=a_headers)

    resp = await client.post(
        f"/api/v1/discovery/sources/{source['id']}/extract", headers=b_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_extract_tenant_b_gets_own_company_not_tenant_a_dedup(
    client: AsyncClient, monkeypatch
):
    """Dedup is per-tenant only: two tenants observing the same domain must
    never collapse into one shared Company row."""
    a_headers = await register_tenant(client, "c3-dedup-a", "c3-dedup-a@example.com")
    b_headers = await register_tenant(client, "c3-dedup-b", "c3-dedup-b@example.com")

    monkeypatch.setattr(discovery_svc, "secure_fetch", _fake_fetch(HTML_PAGE.encode()))

    _job_a, source_a = await _setup_fetched_source(client, a_headers)
    await client.post(f"/api/v1/discovery/sources/{source_a['id']}/fetch", headers=a_headers)
    result_a = await client.post(
        f"/api/v1/discovery/sources/{source_a['id']}/extract", headers=a_headers
    )

    _job_b, source_b = await _setup_fetched_source(client, b_headers)
    await client.post(f"/api/v1/discovery/sources/{source_b['id']}/fetch", headers=b_headers)
    result_b = await client.post(
        f"/api/v1/discovery/sources/{source_b['id']}/extract", headers=b_headers
    )

    assert result_a.json()["company_id"] != result_b.json()["company_id"]


@pytest.mark.asyncio
async def test_extract_requires_manager_role(client: AsyncClient, monkeypatch):
    owner_headers = await register_tenant(client, "c3-rbac", "c3-rbac@example.com")
    _job, source = await _setup_fetched_source(client, owner_headers)
    monkeypatch.setattr(discovery_svc, "secure_fetch", _fake_fetch(HTML_PAGE.encode()))
    await client.post(f"/api/v1/discovery/sources/{source['id']}/fetch", headers=owner_headers)

    viewer_headers = await create_user_with_role(
        client, owner_headers, "c3-viewer@example.com", "viewer"
    )
    resp = await client.post(
        f"/api/v1/discovery/sources/{source['id']}/extract", headers=viewer_headers
    )
    assert resp.status_code == 403
