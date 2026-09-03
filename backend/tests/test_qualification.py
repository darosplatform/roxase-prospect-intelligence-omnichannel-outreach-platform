import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.models.audit import AuditEvent
from tests.conftest import (
    create_company,
    create_evidence,
    create_user_with_role,
    register_tenant,
)


def tenant_id_from_headers(headers: dict):
    return decode_token(headers["Authorization"].split(" ")[1])["tenant_id"]


async def _qual_status(db: AsyncSession, tenant_id: str) -> list[str]:
    result = await db.execute(
        select(AuditEvent.action).where(AuditEvent.tenant_id == tenant_id)
    )
    return list(result.scalars().all())


async def _lead_with_evidence(client, suffix):
    headers = await register_tenant(client, f"qual-{suffix}", f"qual{suffix}@example.com")
    company_id = await create_company(client, headers, suffix)
    ev_id = await create_evidence(client, headers, suffix, company_id)
    lead_resp = await client.post(
        "/api/v1/leads", json={"company_id": company_id}, headers=headers
    )
    lead_id = lead_resp.json()["id"]
    return headers, lead_id, ev_id


@pytest.mark.asyncio
async def test_qualify_candidate_to_qualified(client: AsyncClient):
    headers, lead_id, ev_id = await _lead_with_evidence(client, "up")

    resp = await client.post(
        f"/api/v1/leads/{lead_id}/qualify",
        json={"status": "qualified", "reason": "Strong hiring", "evidence_ids": [ev_id]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["qualification_status"] == "qualified"
    assert resp.json()["qualification_reason"] == "Strong hiring"
    assert resp.json()["qualified_at"] is not None


@pytest.mark.asyncio
async def test_qualify_disqualified(client: AsyncClient):
    headers, lead_id, ev_id = await _lead_with_evidence(client, "disq")

    resp = await client.post(
        f"/api/v1/leads/{lead_id}/qualify",
        json={"status": "disqualified", "reason": "Out of ICP", "evidence_ids": [ev_id]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["qualification_status"] == "disqualified"


@pytest.mark.asyncio
async def test_qualify_requires_evidence(client: AsyncClient):
    headers, lead_id, _ = await _lead_with_evidence(client, "noev")
    resp = await client.post(
        f"/api/v1/leads/{lead_id}/qualify",
        json={"status": "qualified", "reason": "just a number"},
        headers=headers,
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_qualify_rejects_foreign_evidence(client: AsyncClient):
    head_a, lead_id, ev_a = await _lead_with_evidence(client, "x-t1")
    head_b = await register_tenant(client, "qual-x", "qualx@example.com")
    resp = await client.post(
        f"/api/v1/leads/{lead_id}/qualify",
        json={"status": "qualified", "evidence_ids": [ev_a]},
        headers=head_b,
    )
    assert resp.status_code in (403, 404), resp.text


@pytest.mark.asyncio
async def test_qualify_viewer_cannot(client: AsyncClient):
    owner, lead_id, ev_id = await _lead_with_evidence(client, "rb")
    viewer = await create_user_with_role(client, owner, "qual_viewer@example.com", "viewer")
    resp = await client.post(
        f"/api/v1/leads/{lead_id}/qualify",
        json={"status": "qualified", "evidence_ids": [ev_id]},
        headers=viewer,
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_qualify_writes_audit(client: AsyncClient, db_session: AsyncSession):
    headers, lead_id, ev_id = await _lead_with_evidence(client, "audit")
    await client.post(
        f"/api/v1/leads/{lead_id}/qualify",
        json={"status": "qualified", "reason": "For audit", "evidence_ids": [ev_id]},
        headers=headers,
    )
    tid = tenant_id_from_headers(headers)
    events = await _qual_status(db_session, tid)
    assert "lead.qualified" in events


@pytest.mark.asyncio
async def test_qualify_disqualified_writes_audit(
    client: AsyncClient, db_session: AsyncSession
):
    headers, lead_id, ev_id = await _lead_with_evidence(client, "audit2")
    await client.post(
        f"/api/v1/leads/{lead_id}/qualify",
        json={"status": "disqualified", "reason": "Nope", "evidence_ids": [ev_id]},
        headers=headers,
    )
    tid = tenant_id_from_headers(headers)
    events = await _qual_status(db_session, tid)
    assert "lead.disqualified" in events