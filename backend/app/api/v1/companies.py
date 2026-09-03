import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.crud_helpers import apply_sort, paginate, prepare_search
from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.company import Company
from app.models.user import User
from app.schemas.company import CompanyCreate, CompanyRead

router = APIRouter()

SORT_FIELDS = {
    "created_at": Company.created_at,
    "updated_at": Company.updated_at,
    "legal_name": Company.legal_name,
}


@router.get("/companies", response_model=list[CompanyRead])
async def list_companies(
    skip: int = 0,
    limit: int = 50,
    q: str | None = None,
    sort: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[Company]:
    stmt = select(Company).where(Company.tenant_id == user.tenant_id)
    stmt = prepare_search(
        stmt, [Company.legal_name, Company.domain, Company.industry], q
    )
    stmt = apply_sort(stmt, SORT_FIELDS, sort)
    stmt = paginate(stmt, skip, limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/companies", response_model=CompanyRead, status_code=201)
async def create_company(
    payload: CompanyCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> Company:
    company = Company(**payload.model_dump(), tenant_id=user.tenant_id)
    db.add(company)
    await db.flush()
    await db.refresh(company)
    return company


@router.get("/companies/{company_id}", response_model=CompanyRead)
async def get_company(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> Company:
    result = await db.execute(
        select(Company).where(
            Company.id == company_id,
            Company.tenant_id == user.tenant_id,
        )
    )
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company
