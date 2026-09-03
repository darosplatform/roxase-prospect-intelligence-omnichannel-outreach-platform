import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.company import Company
from app.models.contact import Contact
from app.models.evidence import Evidence
from app.models.lead import Lead
from app.models.message_template import MessageTemplate
from app.models.opportunity import Opportunity
from app.models.user import User


async def _assert_exists(
    db: AsyncSession, model, pk: uuid.UUID, tenant_id: uuid.UUID, label: str
) -> None:
    result = await db.execute(
        select(model.id).where(model.id == pk, model.tenant_id == tenant_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")


async def assert_company_in_tenant(
    db: AsyncSession, company_id: uuid.UUID | None, tenant_id: uuid.UUID
) -> None:
    if company_id is None:
        return
    await _assert_exists(db, Company, company_id, tenant_id, "Company")


async def assert_contact_in_tenant(
    db: AsyncSession, contact_id: uuid.UUID | None, tenant_id: uuid.UUID
) -> None:
    if contact_id is None:
        return
    await _assert_exists(db, Contact, contact_id, tenant_id, "Contact")


async def assert_lead_in_tenant(
    db: AsyncSession, lead_id: uuid.UUID | None, tenant_id: uuid.UUID
) -> None:
    if lead_id is None:
        return
    await _assert_exists(db, Lead, lead_id, tenant_id, "Lead")


async def assert_user_in_tenant(
    db: AsyncSession, user_id: uuid.UUID | None, tenant_id: uuid.UUID
) -> None:
    if user_id is None:
        return
    await _assert_exists(db, User, user_id, tenant_id, "User")


async def assert_opportunity_in_tenant(
    db: AsyncSession, opportunity_id: uuid.UUID | None, tenant_id: uuid.UUID
) -> None:
    if opportunity_id is None:
        return
    await _assert_exists(db, Opportunity, opportunity_id, tenant_id, "Opportunity")


async def assert_evidence_in_tenant(
    db: AsyncSession, evidence_id: uuid.UUID | None, tenant_id: uuid.UUID
) -> None:
    if evidence_id is None:
        return
    await _assert_exists(db, Evidence, evidence_id, tenant_id, "Evidence")


async def assert_campaign_in_tenant(
    db: AsyncSession, campaign_id: uuid.UUID | None, tenant_id: uuid.UUID
) -> None:
    if campaign_id is None:
        return
    await _assert_exists(db, Campaign, campaign_id, tenant_id, "Campaign")


async def assert_template_in_tenant(
    db: AsyncSession, template_id: uuid.UUID | None, tenant_id: uuid.UUID
) -> None:
    if template_id is None:
        return
    await _assert_exists(db, MessageTemplate, template_id, tenant_id, "Template")
