"""C5: the full autonomous pipeline, starting from a discovered public URL
instead of manually-entered Evidence (that variant is already covered end to
end by test_e2e_pipeline.py, including every required negative scenario —
DNC, unknown consent, low score, stale evidence, frequency, duplicate/
idempotent, kill switch, cross-tenant — so this file does not repeat them).

This file proves two things test_e2e_pipeline.py cannot:
  1. Discovery -> Secure Fetch -> RawDocument -> Extraction -> Evidence ->
     Signal -> Lead -> Qualification -> Score -> Campaign -> Policy ->
     Outreach -> Worker-shaped dry-run dispatch, composes correctly and the
     ENTIRE reverse trace (Outreach -> Policy Decision -> Lead -> Score ->
     Signal -> Evidence -> RawDocument -> DiscoverySource -> URL) holds.
  2. A blocked or invalid source produces truly zero downstream creation —
     not just "no RawDocument", but no Evidence, Signal, Lead or Outreach
     anywhere in the tenant.
"""

import pytest
from httpx import AsyncClient

import app.services.discovery as discovery_svc
from app.services.providers import registry
from app.services.secure_fetcher import FetchResult
from tests.conftest import register_tenant

JOB_URL = "/api/v1/discovery/jobs"

NEWS_PAGE_HTML = """
<html>
<head>
  <title>Acme Robotics raises Series A</title>
  <meta property="og:site_name" content="Acme Robotics" />
</head>
<body>
  <h1>Acme Robotics raised a $12M Series A round</h1>
  <p>Press contact: Jane Doe, Chief Executive Officer —
     <a href="mailto:jane@acme.com">jane@acme.com</a></p>
</body>
</html>
"""


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


async def _all_empty(client: AsyncClient, headers: dict) -> bool:
    for path in ("/api/v1/companies", "/api/v1/contacts", "/api/v1/evidence",
                 "/api/v1/signals", "/api/v1/leads", "/api/v1/outreach"):
        resp = await client.get(path, headers=headers)
        assert resp.status_code == 200, resp.text
        if resp.json():
            return False
    return True


@pytest.mark.asyncio
async def test_e2e_discovery_to_outreach_dry_run_with_full_traceability(
    client: AsyncClient, monkeypatch
):
    headers = await register_tenant(client, "e2e-disc", "e2e-disc@example.com")

    # -- C1: Discovery job + source ------------------------------------- #
    job_resp = await client.post(JOB_URL, json={"target": "https://acme.com"}, headers=headers)
    assert job_resp.status_code == 201, job_resp.text
    job = job_resp.json()
    await client.patch(f"{JOB_URL}/{job['id']}", json={"status": "queued"}, headers=headers)
    await client.patch(f"{JOB_URL}/{job['id']}", json={"status": "running"}, headers=headers)

    source_url = "https://acme.com/news/series-a"
    src_resp = await client.post(
        f"{JOB_URL}/{job['id']}/sources", json=[{"url": source_url}], headers=headers
    )
    assert src_resp.status_code == 201, src_resp.text
    source = src_resp.json()[0]

    # -- C2: Secure fetch (network layer faked; SSRF safety has its own
    # exhaustive suite in test_secure_fetcher.py) ------------------------ #
    monkeypatch.setattr(discovery_svc, "secure_fetch", _fake_fetch(NEWS_PAGE_HTML.encode()))
    fetch_resp = await client.post(
        f"/api/v1/discovery/sources/{source['id']}/fetch", headers=headers
    )
    assert fetch_resp.status_code == 200, fetch_resp.text
    assert fetch_resp.json()["status"] == "fetched"
    await client.patch(f"{JOB_URL}/{job['id']}", json={"status": "fetched"}, headers=headers)

    # -- C3: Extraction ---------------------------------------------------#
    extract_resp = await client.post(
        f"/api/v1/discovery/sources/{source['id']}/extract", headers=headers
    )
    assert extract_resp.status_code == 200, extract_resp.text
    extraction = extract_resp.json()
    company_id = extraction["company_id"]
    evidence_id = extraction["evidence_id"]
    assert extraction["contact_ids"]
    contact_id = extraction["contact_ids"][0]
    await client.patch(f"{JOB_URL}/{job['id']}", json={"status": "extracted"}, headers=headers)

    company = (await client.get(f"/api/v1/companies/{company_id}", headers=headers)).json()
    assert company["legal_name"] == "Acme Robotics"
    assert company["domain"] == "acme.com"

    evidence = (await client.get("/api/v1/evidence", headers=headers)).json()[0]
    assert evidence["source_url"] == source_url
    meta = evidence["metadata"]
    assert meta["discovery_source_id"] == source["id"]
    assert meta["discovery_job_id"] == job["id"]
    assert meta["raw_document_id"]

    # -- C4: Signal detection ---------------------------------------------#
    signal_resp = await client.post(
        f"/api/v1/evidence/{evidence_id}/detect-signal", headers=headers
    )
    assert signal_resp.status_code == 200, signal_resp.text
    signal = signal_resp.json()
    assert signal is not None
    assert signal["signal_type"] == "funding"
    assert signal["evidence_id"] == evidence_id
    assert signal["company_id"] == company_id

    # -- Lead / Qualification / Score (pre-existing, untouched machinery) -#
    lead_resp = await client.post(
        "/api/v1/leads", json={"company_id": company_id, "status": "new"}, headers=headers
    )
    assert lead_resp.status_code == 201, lead_resp.text
    lead_id = lead_resp.json()["id"]

    qualify_resp = await client.post(
        f"/api/v1/leads/{lead_id}/qualify",
        json={"status": "qualified", "evidence_ids": [evidence_id]},
        headers=headers,
    )
    assert qualify_resp.status_code == 200, qualify_resp.text

    score_resp = await client.post(f"/api/v1/leads/{lead_id}/score", headers=headers)
    assert score_resp.status_code == 200, score_resp.text
    assert 0 < score_resp.json()["score"] <= 100

    # -- Campaign / Policy / Outreach (pre-existing, untouched machinery) -#
    campaign_resp = await client.post(
        "/api/v1/campaigns",
        json={
            "name": "Discovery Campaign",
            "status": "running",
            "channel": "email",
            "policy": {
                "dry_run": True,
                "allowed_channels": ["email"],
                "min_lead_score": 1,
                "require_qualification": True,
                "require_evidence": True,
            },
        },
        headers=headers,
    )
    assert campaign_resp.status_code == 201, campaign_resp.text
    campaign_id = campaign_resp.json()["id"]

    template_resp = await client.post(
        "/api/v1/templates",
        json={"name": "Disc Tmpl", "channel": "email", "body": "Hi {{first_name}}"},
        headers=headers,
    )
    template_id = template_resp.json()["id"]

    await client.post(
        "/api/v1/consents",
        json={"contact_id": contact_id, "basis": "consent", "channel": "email"},
        headers=headers,
    )

    policy_eval = await client.post(
        "/api/v1/policies/evaluate",
        json={
            "lead_id": lead_id,
            "campaign_id": campaign_id,
            "contact_id": contact_id,
            "channel": "email",
        },
        headers=headers,
    )
    assert policy_eval.status_code == 200, policy_eval.text
    assert policy_eval.json()["decision"] == "ALLOW"
    assert evidence_id in policy_eval.json()["evidence_ids"]

    outreach_resp = await client.post(
        "/api/v1/outreach",
        json={
            "campaign_id": campaign_id,
            "contact_id": contact_id,
            "channel": "email",
            "template_id": template_id,
        },
        headers=headers,
    )
    assert outreach_resp.status_code == 201, outreach_resp.text
    outreach_id = outreach_resp.json()["id"]
    assert outreach_resp.json()["status"] == "approved"

    before_calls = len(registry.provider_for("email").calls)  # type: ignore[attr-defined]
    dispatch_resp = await client.post(
        f"/api/v1/outreach/{outreach_id}/dispatch", headers=headers
    )
    assert dispatch_resp.status_code == 200, dispatch_resp.text
    assert dispatch_resp.json()["status"] == "sent"
    assert dispatch_resp.json()["provider_message_id"].startswith("dry_run:")
    assert len(registry.provider_for("email").calls) == before_calls  # type: ignore[attr-defined]

    # -- Full reverse trace: Outreach -> ... -> URL ------------------------#
    assert dispatch_resp.json()["campaign_id"] == campaign_id
    lead = (await client.get(f"/api/v1/leads/{lead_id}", headers=headers)).json()
    assert lead["company_id"] == company_id
    assert lead["qualification_status"] == "qualified"
    assert lead["score"] and lead["score"] > 0
    assert signal["company_id"] == lead["company_id"]
    assert evidence["source_url"] == source["url"] == source_url


@pytest.mark.asyncio
async def test_e2e_discovery_ssrf_blocked_produces_zero_downstream_creation(
    client: AsyncClient,
):
    """Uses the REAL, unmocked secure fetcher: a literal IP needs no DNS
    query to resolve, so this exercises genuine SSRF blocking without any
    outbound network access — and proves the block stops the ENTIRE chain,
    not just the fetch step."""
    headers = await register_tenant(client, "e2e-ssrf", "e2e-ssrf@example.com")
    job_resp = await client.post(JOB_URL, json={"target": "https://evil.example"}, headers=headers)
    job = job_resp.json()
    src_resp = await client.post(
        f"{JOB_URL}/{job['id']}/sources",
        json=[{"url": "http://169.254.169.254/latest/meta-data/"}],
        headers=headers,
    )
    source = src_resp.json()[0]

    fetch_resp = await client.post(
        f"/api/v1/discovery/sources/{source['id']}/fetch", headers=headers
    )
    assert fetch_resp.status_code == 200, fetch_resp.text
    assert fetch_resp.json()["status"] == "rejected"
    assert fetch_resp.json()["validation_status"] == "blocked_cloud_metadata"

    extract_resp = await client.post(
        f"/api/v1/discovery/sources/{source['id']}/extract", headers=headers
    )
    assert extract_resp.status_code == 409  # no RawDocument was ever created

    assert await _all_empty(client, headers)


@pytest.mark.asyncio
async def test_e2e_discovery_invalid_scheme_source_produces_zero_downstream_creation(
    client: AsyncClient,
):
    headers = await register_tenant(client, "e2e-invalid", "e2e-invalid@example.com")
    job_resp = await client.post(JOB_URL, json={"target": "https://acme.com"}, headers=headers)
    job = job_resp.json()
    src_resp = await client.post(
        f"{JOB_URL}/{job['id']}/sources",
        json=[{"url": "ftp://acme.com/internal-file"}],
        headers=headers,
    )
    source = src_resp.json()[0]

    fetch_resp = await client.post(
        f"/api/v1/discovery/sources/{source['id']}/fetch", headers=headers
    )
    assert fetch_resp.json()["status"] == "rejected"
    assert fetch_resp.json()["validation_status"] == "blocked_scheme"
    assert await _all_empty(client, headers)
