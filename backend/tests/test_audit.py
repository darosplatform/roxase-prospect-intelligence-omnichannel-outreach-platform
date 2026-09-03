import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.models.audit import AuditEvent
from tests.conftest import create_company, register_tenant


def tenant_id_from_headers(headers: dict):
    return decode_token(headers["Authorization"].split(" ")[1])["tenant_id"]


async def _action_count(db: AsyncSession, action: str, tenant_id: str) -> int:
    result = await db.execute(
        select(AuditEvent).where(
            AuditEvent.action == action,
            AuditEvent.tenant_id == tenant_id,
        )
    )
    return len(list(result.scalars().all()))


@pytest.mark.asyncio
async def test_audit_records_signal_create(client: AsyncClient, db_session: AsyncSession):
    headers = await register_tenant(client, "audit-opp", "audit_opp@example.com")
    company_id = await create_company(client, headers, "Opp")

    resp = await client.post(
        "/api/v1/signals",
        json={"company_id": company_id, "signal_type": "funding"},
        headers=headers,
    )
    assert resp.status_code == 201

    tenant_id = tenant_id_from_headers(headers)
    assert await _action_count(db_session, "signal.created", tenant_id) == 1


@pytest.mark.asyncio
async def test_audit_records_campaign_create(client: AsyncClient, db_session: AsyncSession):
    headers = await register_tenant(client, "audit-camp", "audit_camp@example.com")

    resp = await client.post("/api/v1/campaigns", json={"name": "Camp"}, headers=headers)
    assert resp.status_code == 201

    tenant_id = tenant_id_from_headers(headers)
    assert await _action_count(db_session, "campaign.created", tenant_id) == 1


@pytest.mark.asyncio
async def test_audit_records_stage_change(client: AsyncClient, db_session: AsyncSession):
    headers = await register_tenant(client, "audit-stage", "audit_stage@example.com")
    company_id = await create_company(client, headers, "Stage")
    create_resp = await client.post(
        "/api/v1/opportunities",
        json={"company_id": company_id, "name": "Deal"},
        headers=headers,
    )
    opp_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/api/v1/opportunities/{opp_id}",
        json={"stage": "qualified"},
        headers=headers,
    )
    assert patch_resp.status_code == 200

    tenant_id = tenant_id_from_headers(headers)
    assert await _action_count(db_session, "opportunity.stage_changed", tenant_id) == 1


@pytest.mark.asyncio
async def test_audit_records_task_completed(client: AsyncClient, db_session: AsyncSession):
    headers = await register_tenant(client, "audit-task", "audit_task@example.com")
    create_resp = await client.post("/api/v1/tasks", json={"title": "T"}, headers=headers)
    task_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/api/v1/tasks/{task_id}", json={"status": "done"}, headers=headers
    )
    assert patch_resp.status_code == 200

    tenant_id = tenant_id_from_headers(headers)
    assert await _action_count(db_session, "task.completed", tenant_id) == 1