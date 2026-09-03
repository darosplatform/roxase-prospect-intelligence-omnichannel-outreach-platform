from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.v1.activities import router as activities_router
from app.api.v1.auth import router as auth_router
from app.api.v1.campaigns import router as campaigns_router
from app.api.v1.companies import router as companies_router
from app.api.v1.contacts import router as contacts_router
from app.api.v1.leads import router as leads_router
from app.api.v1.notes import router as notes_router
from app.api.v1.opportunities import router as opportunities_router
from app.api.v1.signals import router as signals_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.tenants import router as tenants_router
from app.api.v1.workspaces import router as workspaces_router

app = FastAPI(
    title="ROXASE API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(health_router)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(tenants_router, prefix="/api/v1")
app.include_router(workspaces_router, prefix="/api/v1")
app.include_router(companies_router, prefix="/api/v1", tags=["companies"])
app.include_router(contacts_router, prefix="/api/v1", tags=["contacts"])
app.include_router(leads_router, prefix="/api/v1", tags=["leads"])
app.include_router(signals_router, prefix="/api/v1", tags=["signals"])
app.include_router(opportunities_router, prefix="/api/v1", tags=["opportunities"])
app.include_router(activities_router, prefix="/api/v1", tags=["activities"])
app.include_router(tasks_router, prefix="/api/v1", tags=["tasks"])
app.include_router(notes_router, prefix="/api/v1", tags=["notes"])
app.include_router(campaigns_router, prefix="/api/v1", tags=["campaigns"])
