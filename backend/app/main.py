from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.v1.companies import router as companies_router
from app.api.v1.contacts import router as contacts_router
from app.api.v1.leads import router as leads_router

app = FastAPI(
    title="ROXASE API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(health_router)
app.include_router(companies_router, prefix="/api/v1", tags=["companies"])
app.include_router(contacts_router, prefix="/api/v1", tags=["contacts"])
app.include_router(leads_router, prefix="/api/v1", tags=["leads"])
