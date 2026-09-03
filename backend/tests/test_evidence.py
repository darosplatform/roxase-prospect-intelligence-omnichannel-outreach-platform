import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.models.audit import AuditEvent
from tests.conftest import (
    create_company,
    create_contact,
    create_evidence,
    create_lead,
    create_user_with_role,
    register_tenant,
)


def tenant_id_from_headers(headers: dict):
    return decode_token(headers["Authorization"].split(" ")[1])["tenant_id"]


async def _action_count(db: AsyncSession, action: str, tenant_id: str) -> int:
    result = await db.execute(
        select(AuditEvent).where(
            AuditEvent.action == action, AuditEvent.tenant_id == tenant_id
        )
    )
    return len(list(result.scalars().all()))


@pytest.mark.asyncio
async def test_evidence_create_and_read(client: AsyncClient):
    headers = await register_tenant(client, "ev-create", "ev_create@example.com")
    company_id = await create_company(client, headers, "Ev")
    contact_id = await create_contact(client, headers, "Ev")
    lead_id = await create_lead(client, headers, "Ev")

    resp = await client.post(
        "/api/v1/evidence",
        json={
            "source_url": "https://ev.com/r1",
            "source_name": "TechCrunch",
            "evidence_type": "news",
            "title": "Funding round",
            "excerpt": "The company raised a round.",
            "company_id": company_id,
            "contact_id": contact_id,
            "lead_id": lead_id,
            "confidence": 0.9,
            "metadata": {"reach": 10000},
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["evidence_type"] == "news"
    assert data["source_name"] == "TechCrunch"
    assert data["confidence"] == 0.9
    assert data["metadata"] == {"reach": 10000}
    assert data["lead_id"] == lead_id

    list_resp = await client.get("/api/v1/evidence", headers=headers)
    assert list_resp.status_code == 200
    assert any(e["id"] == data["id"] for e in list_resp.json())


@pytest.mark.asyncio
async def test_evidence_tenant_isolation(client: AsyncClient):
    head_a = await register_tenant(client, "ev-a", "eva@example.com")
    company_a = await create_company(client, head_a, "A")
    ev_id = await create_evidence(client, head_a, "A", company_a)

    head_b = await register_tenant(client, "ev-b", "evb@example.com")
    list_b = await client.get("/api/v1/evidence", headers=head_b)
    assert list_b.status_code == 200
    assert all(e["id"] != ev_id for e in list_b.json())


@pytest.mark.asyncio
async def test_evidence_rejects_foreign_company(client: AsyncClient):
    head_a = await register_tenant(client, "evfa", "evfa@example.com")
    company_a = await create_company(client, head_a, "A")
    head_b = await register_tenant(client, "evfb", "evfb@example.com")

    resp = await client.post(
        "/api/v1/evidence",
        json={"source_url": "https://x/y", "company_id": company_a},
        headers=head_b,
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_evidence_viewer_cannot_create(client: AsyncClient):
    owner = await register_tenant(client, "ev-rbac", "ev_rbac@example.com")
    viewer = await create_user_with_role(
        client, owner, "ev_viewer@example.com", "viewer"
    )
    resp = await client.post(
        "/api/v1/evidence",
        json={"source_url": "https://x/y"},
        headers=viewer,
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_evidence_audit_created(client: AsyncClient, db_session: AsyncSession):
    headers = await register_tenant(client, "ev-audit", "ev_audit@example.com")
    company_id = await create_company(client, headers, "A")
    await create_evidence(client, headers, "A", company_id)

    tid = tenant_id_from_headers(headers)
    assert await _action_count(db_session, "evidence.created", tid) == 1