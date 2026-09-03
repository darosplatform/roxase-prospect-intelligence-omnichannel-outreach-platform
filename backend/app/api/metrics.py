"""Metrics exposition endpoint (Prometheus text format)."""

from fastapi import APIRouter, Response

from app.core import request_stats
from app.core.metrics import metrics

router = APIRouter()


@router.get("/metrics")
async def metrics_endpoint() -> Response:
    # Fold in request-level statistics held by the app middleware.
    request_stats.fold_into(metrics)
    body = metrics.render_prometheus()
    return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")