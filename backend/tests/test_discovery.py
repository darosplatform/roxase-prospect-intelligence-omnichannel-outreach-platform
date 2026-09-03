import pytest
from httpx import AsyncClient

from tests.conftest import create_user_with_role, register_tenant

JOB_URL = "/api/v1/discovery/jobs"


async def _create_job(client, headers, target="https://example.com"):
    resp = await client.post(JOB_URL, json={"target": target}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _register(client, slug, email):
    return await register_tenant(client, slug, email)


@pytest.mark.asyncio
async def test_create_job(client: AsyncClient):
    headers = await _register(client, "disc-create", "disc-create@example.com")
    job = await _create_job(client, headers)
    assert job["status"] == "draft"
    assert job["source_type"] == "url"
    assert job["tenant_id"]


@pytest.mark.asyncio
async def test_create_job_dedups_by_target(client: AsyncClient):
    headers = await _register(client, "disc-dedup", "disc-dedup@example.com")
    first = await _create_job(client, headers, "HTTPS://Example.com/")
    second = await _create_job(client, headers, "https://example.com")
    # Canonical target hash: same normalized target should collide.
    assert first["id"] == second["id"]


@pytest.mark.asyncio
async def test_job_tenant_isolation(client: AsyncClient):
    a_headers = await _register(client, "disc-iso-a", "disc-iso-a@example.com")
    b_headers = await _register(client, "disc-iso-b", "disc-iso-b@example.com")
    job = await _create_job(client, a_headers, "https://tenant-a.com")

    b_list = await client.get(JOB_URL, headers=b_headers)
    assert b_list.status_code == 200
    assert b_list.json() == []

    # Tenant B cannot read tenant A's job (nor its sources).
    b_get = await client.get(f"{JOB_URL}/{job['id']}", headers=b_headers)
    assert b_get.status_code == 404
    b_sources = await client.get(f"{JOB_URL}/{job['id']}/sources", headers=b_headers)
    assert b_sources.status_code == 404


@pytest.mark.asyncio
async def test_requires_role_for_create(client: AsyncClient):
    owner_headers = await _register(client, "disc-rbac", "disc-rbac@example.com")
    viewer_headers = await create_user_with_role(
        client, owner_headers, "disc-viewer@example.com", "viewer"
    )
    resp = await client.post(JOB_URL, json={"target": "https://x.com"}, headers=viewer_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_job_state_transitions_validated(client: AsyncClient):
    headers = await _register(client, "disc-state", "disc-state@example.com")
    job = await _create_job(client, headers)

    # draft -> done is NOT a valid transition.
    bad = await client.patch(
        f"{JOB_URL}/{job['id']}", json={"status": "done"}, headers=headers
    )
    assert bad.status_code == 409

    # draft -> queued -> running is valid.
    ok = await client.patch(
        f"{JOB_URL}/{job['id']}", json={"status": "queued"}, headers=headers
    )
    assert ok.status_code == 200
    ok2 = await client.patch(
        f"{JOB_URL}/{job['id']}", json={"status": "running"}, headers=headers
    )
    assert ok2.status_code == 200
    assert ok2.json()["status"] == "running"


@pytest.mark.asyncio
async def test_add_sources_and_dedup(client: AsyncClient):
    headers = await _register(client, "disc-src", "disc-src@example.com")
    job = await _create_job(client, headers, "https://corp.example.com")

    payload = [
        {"url": "https://corp.example.com/about"},
        {"url": "HTTPS://CORP.example.com/about/"},
    ]
    resp = await client.post(
        f"{JOB_URL}/{job['id']}/sources", json=payload, headers=headers
    )
    assert resp.status_code == 201, resp.text
    sources = resp.json()
    # Canonicalization collides both URLs into one source.
    assert len(sources) == 1

    listed = await client.get(f"{JOB_URL}/{job['id']}/sources", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["url_hash"] == sources[0]["url_hash"]


@pytest.mark.asyncio
async def test_source_tenant_isolation(client: AsyncClient):
    a_headers = await _register(client, "disc-src-a", "disc-src-a@example.com")
    b_headers = await _register(client, "disc-src-b", "disc-src-b@example.com")
    job = await _create_job(client, a_headers, "https://corp-a.com")
    created = await client.post(
        f"{JOB_URL}/{job['id']}/sources",
        json=[{"url": "https://corp-a.com/r"}],
        headers=a_headers,
    )
    assert created.status_code == 201
    source_id = created.json()[0]["id"]

    # Tenant B cannot read tenant A's source.
    b_get = await client.get(f"/api/v1/discovery/sources/{source_id}", headers=b_headers)
    assert b_get.status_code == 404


@pytest.mark.asyncio
async def test_store_raw_document_and_dedup(client: AsyncClient):
    headers = await _register(client, "disc-raw", "disc-raw@example.com")
    job = await _create_job(client, headers, "https://raw.example.com")
    created = await client.post(
        f"{JOB_URL}/{job['id']}/sources",
        json=[{"url": "https://raw.example.com/page"}],
        headers=headers,
    )
    source_id = created.json()[0]["id"]

    payload = {
        "source_id": source_id,
        "job_id": job["id"],
        "fetch_url": "https://raw.example.com/page",
        "content_type": "text/html",
        "content_body": "<html>raw body</html>",
    }
    doc = await client.post("/api/v1/discovery/raw", json=payload, headers=headers)
    assert doc.status_code == 201, doc.text
    assert doc.json()["content_hash"]
    assert doc.json()["size_bytes"] == len(b"<html>raw body</html>")

    # Same body -> dedup returns the same raw document (content-hash collision).
    dup = await client.post("/api/v1/discovery/raw", json=payload, headers=headers)
    assert dup.status_code == 201
    assert dup.json()["id"] == doc.json()["id"]


@pytest.mark.asyncio
async def test_store_raw_document_source_job_mismatch(client: AsyncClient):
    headers = await _register(client, "disc-mismatch", "disc-mismatch@example.com")
    job_a = await _create_job(client, headers, "https://a.example.com")
    job_b = await _create_job(client, headers, "https://b.example.com")
    created = await client.post(
        f"{JOB_URL}/{job_a['id']}/sources",
        json=[{"url": "https://a.example.com/r"}],
        headers=headers,
    )
    source_id = created.json()[0]["id"]

    payload = {
        "source_id": source_id,
        "job_id": job_b["id"],  # source belongs to job_a, not job_b
        "fetch_url": "https://a.example.com/r",
        "content_body": "x",
    }
    resp = await client.post("/api/v1/discovery/raw", json=payload, headers=headers)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_store_raw_document_tenant_guard(client: AsyncClient):
    a_headers = await _register(client, "disc-raw-a", "disc-raw-a@example.com")
    b_headers = await _register(client, "disc-raw-b", "disc-raw-b@example.com")
    job = await _create_job(client, a_headers, "https://raw-a.example.com")
    created = await client.post(
        f"{JOB_URL}/{job['id']}/sources",
        json=[{"url": "https://raw-a.example.com/r"}],
        headers=a_headers,
    )
    source_id = created.json()[0]["id"]

    payload = {
        "source_id": source_id,
        "job_id": job["id"],
        "fetch_url": "https://raw-a.example.com/r",
        "content_body": "y",
    }
    resp = await client.post("/api/v1/discovery/raw", json=payload, headers=b_headers)
    assert resp.status_code == 404