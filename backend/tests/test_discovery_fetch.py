"""C2 integration: POST /discovery/sources/{id}/fetch end to end against the
real API + DB, with the network layer replaced by a fake secure_fetch (no
real sockets). Confirms the C1/C2 boundary: a fetch — success or SSRF block —
never creates Evidence, Signal or Lead rows.
"""

import hashlib

import pytest
from httpx import AsyncClient

import app.services.discovery as discovery_svc
from app.services.secure_fetcher import FetchResult, SecureFetchError
from tests.conftest import create_user_with_role, register_tenant

JOB_URL = "/api/v1/discovery/jobs"


async def _setup_source(client, headers, url="https://example.com/about"):
    job_resp = await client.post(JOB_URL, json={"target": "https://example.com"}, headers=headers)
    assert job_resp.status_code == 201, job_resp.text
    job = job_resp.json()
    src_resp = await client.post(
        f"{JOB_URL}/{job['id']}/sources", json=[{"url": url}], headers=headers
    )
    assert src_resp.status_code == 201, src_resp.text
    return job, src_resp.json()[0]


async def _no_evidence_signal_lead(client: AsyncClient, headers: dict) -> bool:
    for path in ("/api/v1/evidence", "/api/v1/signals", "/api/v1/leads"):
        resp = await client.get(path, headers=headers)
        assert resp.status_code == 200, resp.text
        if resp.json():
            return False
    return True


@pytest.mark.asyncio
async def test_fetch_success_creates_raw_document_and_updates_source(
    client: AsyncClient, monkeypatch
):
    headers = await register_tenant(client, "c2-ok", "c2-ok@example.com")
    _job, source = await _setup_source(client, headers)

    body = b"<html><body>hello world</body></html>"

    async def fake_secure_fetch(url, **_kwargs):
        return FetchResult(
            final_url=url,
            status_code=200,
            content_type="text/html",
            body=body,
            resolved_ip="93.184.216.34",
            redirect_chain=[],
            elapsed_seconds=0.01,
        )

    monkeypatch.setattr(discovery_svc, "secure_fetch", fake_secure_fetch)

    resp = await client.post(f"/api/v1/discovery/sources/{source['id']}/fetch", headers=headers)
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["status"] == "fetched"
    assert updated["http_status"] == 200
    assert updated["raw_size"] == len(body)
    # content_hash is derived server-side from the fetched body, never trusted
    # from the caller (there is no client input carrying a hash at all here).
    assert updated["content_hash"] == hashlib.sha256(body).hexdigest()


@pytest.mark.asyncio
async def test_fetch_ssrf_blocked_marks_source_rejected_no_raw_document(
    client: AsyncClient, monkeypatch
):
    headers = await register_tenant(client, "c2-ssrf", "c2-ssrf@example.com")
    _job, source = await _setup_source(client, headers, url="http://169.254.169.254/latest/meta")

    async def fake_secure_fetch(url, **_kwargs):
        raise SecureFetchError("blocked_cloud_metadata", "blocked cloud metadata endpoint")

    monkeypatch.setattr(discovery_svc, "secure_fetch", fake_secure_fetch)

    resp = await client.post(f"/api/v1/discovery/sources/{source['id']}/fetch", headers=headers)
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["status"] == "rejected"
    assert updated["validation_status"] == "blocked_cloud_metadata"
    assert updated["content_hash"] is None
    assert updated["raw_size"] is None


@pytest.mark.asyncio
async def test_fetch_network_failure_marks_source_failed(
    client: AsyncClient, monkeypatch
):
    headers = await register_tenant(client, "c2-fail", "c2-fail@example.com")
    _job, source = await _setup_source(client, headers)

    async def fake_secure_fetch(url, **_kwargs):
        raise SecureFetchError("timeout", "total fetch timeout exceeded")

    monkeypatch.setattr(discovery_svc, "secure_fetch", fake_secure_fetch)

    resp = await client.post(f"/api/v1/discovery/sources/{source['id']}/fetch", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "failed"


@pytest.mark.asyncio
async def test_fetch_never_creates_evidence_signal_or_lead(
    client: AsyncClient, monkeypatch
):
    headers = await register_tenant(client, "c2-boundary", "c2-boundary@example.com")
    _job, source = await _setup_source(client, headers)

    async def fake_secure_fetch(url, **_kwargs):
        return FetchResult(
            final_url=url,
            status_code=200,
            content_type="text/html",
            body=b"<html>lots of business signal words: hiring, funding</html>",
            resolved_ip="93.184.216.34",
            redirect_chain=[],
            elapsed_seconds=0.01,
        )

    monkeypatch.setattr(discovery_svc, "secure_fetch", fake_secure_fetch)

    resp = await client.post(f"/api/v1/discovery/sources/{source['id']}/fetch", headers=headers)
    assert resp.status_code == 200, resp.text
    assert await _no_evidence_signal_lead(client, headers)


@pytest.mark.asyncio
async def test_fetch_cross_tenant_returns_404(client: AsyncClient, monkeypatch):
    a_headers = await register_tenant(client, "c2-iso-a", "c2-iso-a@example.com")
    b_headers = await register_tenant(client, "c2-iso-b", "c2-iso-b@example.com")
    _job, source = await _setup_source(client, a_headers)

    resp = await client.post(
        f"/api/v1/discovery/sources/{source['id']}/fetch", headers=b_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_fetch_requires_manager_role(client: AsyncClient):
    owner_headers = await register_tenant(client, "c2-rbac", "c2-rbac@example.com")
    _job, source = await _setup_source(client, owner_headers)
    viewer_headers = await create_user_with_role(
        client, owner_headers, "c2-viewer@example.com", "viewer"
    )
    resp = await client.post(
        f"/api/v1/discovery/sources/{source['id']}/fetch", headers=viewer_headers
    )
    assert resp.status_code == 403
