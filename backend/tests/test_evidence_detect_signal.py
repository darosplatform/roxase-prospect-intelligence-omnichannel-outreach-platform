"""C4 integration: POST /evidence/{id}/detect-signal against the real API + DB."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.signal import Signal
from tests.conftest import create_company, create_user_with_role, register_tenant


async def _create_evidence(
    client: AsyncClient,
    headers: dict,
    company_id: str,
    *,
    evidence_type: str,
    title: str = "",
    excerpt: str = "",
    confidence: float = 1.0,
) -> str:
    resp = await client.post(
        "/api/v1/evidence",
        json={
            "company_id": company_id,
            "source_url": "https://acme.com/careers",
            "source_name": "acme.com",
            "evidence_type": evidence_type,
            "title": title,
            "excerpt": excerpt,
            "confidence": confidence,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_detect_signal_direct_evidence_type_creates_signal(client: AsyncClient):
    headers = await register_tenant(client, "c4-hiring", "c4-hiring@example.com")
    company_id = await create_company(client, headers, "hiring")
    evidence_id = await _create_evidence(client, headers, company_id, evidence_type="hiring")

    resp = await client.post(f"/api/v1/evidence/{evidence_id}/detect-signal", headers=headers)
    assert resp.status_code == 200, resp.text
    signal = resp.json()
    assert signal is not None
    assert signal["signal_type"] == "hiring"
    assert signal["company_id"] == company_id
    assert signal["evidence_id"] == evidence_id
    assert signal["source_url"] == "https://acme.com/careers"
    assert signal["confidence"] == 0.85
    assert signal["status"] == "new"


@pytest.mark.asyncio
async def test_detect_signal_no_support_returns_null(client: AsyncClient):
    headers = await register_tenant(client, "c4-none", "c4-none@example.com")
    company_id = await create_company(client, headers, "none")
    evidence_id = await _create_evidence(
        client, headers, company_id, evidence_type="website", title="Welcome to our site"
    )

    resp = await client.post(f"/api/v1/evidence/{evidence_id}/detect-signal", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() is None

    signals = await client.get("/api/v1/signals", headers=headers)
    assert signals.json() == []


@pytest.mark.asyncio
async def test_detect_signal_confidence_capped_by_evidence_confidence(client: AsyncClient):
    headers = await register_tenant(client, "c4-conf", "c4-conf@example.com")
    company_id = await create_company(client, headers, "conf")
    # Evidence confidence (0.5) is lower than the detector's own base (0.85)
    # for a direct "hiring" prior — the Signal must never exceed 0.5.
    evidence_id = await _create_evidence(
        client, headers, company_id, evidence_type="hiring", confidence=0.5
    )

    resp = await client.post(f"/api/v1/evidence/{evidence_id}/detect-signal", headers=headers)
    assert resp.json()["confidence"] == 0.5


@pytest.mark.asyncio
async def test_detect_signal_broad_scan_from_keyword_only(client: AsyncClient):
    headers = await register_tenant(client, "c4-broad", "c4-broad@example.com")
    company_id = await create_company(client, headers, "broad")
    evidence_id = await _create_evidence(
        client,
        headers,
        company_id,
        evidence_type="website",
        excerpt="Acme just raised a $10M Series A round.",
    )
    resp = await client.post(f"/api/v1/evidence/{evidence_id}/detect-signal", headers=headers)
    signal = resp.json()
    assert signal["signal_type"] == "funding"
    assert signal["confidence"] == 0.6


@pytest.mark.asyncio
async def test_detect_signal_is_idempotent(client: AsyncClient):
    headers = await register_tenant(client, "c4-idem", "c4-idem@example.com")
    company_id = await create_company(client, headers, "idem")
    evidence_id = await _create_evidence(client, headers, company_id, evidence_type="funding")

    first = await client.post(f"/api/v1/evidence/{evidence_id}/detect-signal", headers=headers)
    second = await client.post(f"/api/v1/evidence/{evidence_id}/detect-signal", headers=headers)
    assert first.json()["id"] == second.json()["id"]

    signals = await client.get("/api/v1/signals", headers=headers)
    assert len(signals.json()) == 1


@pytest.mark.asyncio
async def test_detect_signal_does_not_resurrect_dismissed_signal(
    client: AsyncClient, db_session: AsyncSession
):
    headers = await register_tenant(client, "c4-dismiss", "c4-dismiss@example.com")
    company_id = await create_company(client, headers, "dismiss")
    evidence_id = await _create_evidence(client, headers, company_id, evidence_type="acquisition")

    first = await client.post(f"/api/v1/evidence/{evidence_id}/detect-signal", headers=headers)
    signal_id = first.json()["id"]

    row = await db_session.get(Signal, signal_id)
    row.status = "dismissed"
    await db_session.commit()

    second = await client.post(f"/api/v1/evidence/{evidence_id}/detect-signal", headers=headers)
    assert second.json()["id"] == signal_id
    assert second.json()["status"] == "dismissed"  # not flipped back to "new"

    result = await db_session.execute(select(Signal).where(Signal.tenant_id == row.tenant_id))
    assert len(result.scalars().all()) == 1  # no duplicate created alongside it


@pytest.mark.asyncio
async def test_detect_signal_requires_evidence_in_own_tenant(client: AsyncClient):
    a_headers = await register_tenant(client, "c4-iso-a", "c4-iso-a@example.com")
    b_headers = await register_tenant(client, "c4-iso-b", "c4-iso-b@example.com")
    company_id = await create_company(client, a_headers, "iso")
    evidence_id = await _create_evidence(client, a_headers, company_id, evidence_type="hiring")

    resp = await client.post(
        f"/api/v1/evidence/{evidence_id}/detect-signal", headers=b_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_detect_signal_requires_manager_role(client: AsyncClient):
    owner_headers = await register_tenant(client, "c4-rbac", "c4-rbac@example.com")
    company_id = await create_company(client, owner_headers, "rbac")
    evidence_id = await _create_evidence(
        client, owner_headers, company_id, evidence_type="hiring"
    )
    viewer_headers = await create_user_with_role(
        client, owner_headers, "c4-viewer@example.com", "viewer"
    )
    resp = await client.post(
        f"/api/v1/evidence/{evidence_id}/detect-signal", headers=viewer_headers
    )
    assert resp.status_code == 403
