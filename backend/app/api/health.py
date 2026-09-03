"""Health probe endpoints.

* GET /health       — liveness (process responds). Backwards compatible.
* GET /health/live  — liveness (same as /health).
* GET /health/ready — readiness: pings PostgreSQL and Redis; 200 only if both
                      reachable, else 503 with per-component status.
"""

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.cache import get_redis
from app.core.config import settings
from app.db.session import engine

router = APIRouter()


def _liveness_body() -> dict:
    return {"status": "ok", "version": settings.version, "env": settings.env}


@router.get("/health")
async def health() -> dict:
    return _liveness_body()


@router.get("/health/live")
async def health_live() -> dict:
    return _liveness_body()


@router.get("/health/ready")
async def health_ready(response: Response) -> dict:
    checks: dict[str, str] = {}

    # PostgreSQL
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"

    # Redis
    try:
        redis = get_redis()
        pong = await redis.ping()
        checks["redis"] = "ok" if pong else "error"
    except Exception:
        checks["redis"] = "error"

    ready = all(v == "ok" for v in checks.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if ready else "degraded", "checks": checks}