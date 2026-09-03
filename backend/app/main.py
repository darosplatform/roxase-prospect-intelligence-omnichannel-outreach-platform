from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.metrics import router as metrics_router
from app.api.v1.activities import router as activities_router
from app.api.v1.auth import router as auth_router
from app.api.v1.campaigns import router as campaigns_router
from app.api.v1.companies import router as companies_router
from app.api.v1.contacts import router as contacts_router
from app.api.v1.do_not_contact import router as dnc_router
from app.api.v1.evidence import router as evidence_router
from app.api.v1.leads import router as leads_router
from app.api.v1.notes import router as notes_router
from app.api.v1.opportunities import router as opportunities_router
from app.api.v1.outreach import router as outreach_router
from app.api.v1.policies import router as policies_router
from app.api.v1.signals import router as signals_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.templates import router as templates_router
from app.api.v1.tenants import router as tenants_router
from app.api.v1.workspaces import router as workspaces_router
from app.core.cache import close_redis
from app.core.config import settings, validate_production
from app.core.logging_config import configure_logging
from app.middleware.request_id import RequestIdMiddleware


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_production(settings)
    configure_logging(settings.log_json)
    yield
    await close_redis()


app = FastAPI(
    title="ROXASE API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(RequestIdMiddleware)

app.include_router(health_router)
app.include_router(metrics_router)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(tenants_router, prefix="/api/v1")
app.include_router(workspaces_router, prefix="/api/v1")
app.include_router(companies_router, prefix="/api/v1", tags=["companies"])
app.include_router(contacts_router, prefix="/api/v1", tags=["contacts"])
app.include_router(leads_router, prefix="/api/v1", tags=["leads"])
app.include_router(signals_router, prefix="/api/v1", tags=["signals"])
app.include_router(evidence_router, prefix="/api/v1", tags=["evidence"])
app.include_router(policies_router, prefix="/api/v1", tags=["policies"])
app.include_router(outreach_router, prefix="/api/v1", tags=["outreach"])
app.include_router(templates_router, prefix="/api/v1", tags=["templates"])
app.include_router(dnc_router, prefix="/api/v1", tags=["do-not-contact"])
app.include_router(opportunities_router, prefix="/api/v1", tags=["opportunities"])
app.include_router(activities_router, prefix="/api/v1", tags=["activities"])
app.include_router(tasks_router, prefix="/api/v1", tags=["tasks"])
app.include_router(notes_router, prefix="/api/v1", tags=["notes"])
app.include_router(campaigns_router, prefix="/api/v1", tags=["campaigns"])
