from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limits import default_limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse
from app.schemas.user import UserCreate

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    payload: UserCreate,
    slug: str,
    tenant_name: str | None = None,
    _ratelimit=Depends(default_limiter),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    existing_slug = await db.execute(select(Tenant).where(Tenant.slug == slug))
    if existing_slug.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tenant with this slug already exists",
        )
    existing_email = await db.execute(select(User).where(User.email == payload.email))
    if existing_email.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists",
        )

    tenant = Tenant(name=tenant_name or payload.email, slug=slug)
    db.add(tenant)
    await db.flush()

    default_workspace = Workspace(name="Default", tenant_id=tenant.id)
    db.add(default_workspace)
    await db.flush()

    user = User(
        tenant_id=tenant.id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    await db.flush()

    owner = WorkspaceMember(
        workspace_id=default_workspace.id,
        user_id=user.id,
        role="owner",
    )
    db.add(owner)
    await db.flush()

    token_data = {"sub": str(user.id), "tenant_id": str(tenant.id)}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    _ratelimit=Depends(default_limiter),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token_data = {"sub": str(user.id), "tenant_id": str(user.tenant_id)}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshRequest,
    _ratelimit=Depends(default_limiter),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    decoded = decode_token(payload.refresh_token)
    if decoded is None or decoded.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    user_id = decoded.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    token_data = {"sub": str(user.id), "tenant_id": str(user.tenant_id)}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )


@router.post("/users", response_model=TokenResponse, status_code=201)
async def create_user_in_tenant(
    tenant_id: str,
    email: str,
    password: str,
    full_name: str | None = None,
    role: str = "owner",
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    import uuid as _uuid

    tid = _uuid.UUID(tenant_id)
    result = await db.execute(select(Tenant).where(Tenant.id == tid))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    existing_user = await db.execute(select(User).where(User.email == email))
    if existing_user.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User with this email already exists")

    user = User(
        tenant_id=tid,
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
    )
    db.add(user)
    await db.flush()

    workspaces_result = await db.execute(
        select(Workspace).where(Workspace.tenant_id == tid).limit(1)
    )
    workspace = workspaces_result.scalar_one_or_none()
    if workspace:
        member = WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role=role,
        )
        db.add(member)
        await db.flush()

    token_data = {"sub": str(user.id), "tenant_id": str(user.tenant_id)}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )
