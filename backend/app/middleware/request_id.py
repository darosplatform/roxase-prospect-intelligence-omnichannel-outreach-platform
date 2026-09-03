"""HTTP middleware: request-id correlation + request statistics.

Generates (or honours an incoming) `X-Request-ID`, binds it to the logging
contextvar so structured logs carry it, records HTTP statistics for /metrics and
emits a single per-request access log line.
"""

from __future__ import annotations

import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core import request_stats
from app.core.logging_config import request_id_var

logger = logging.getLogger("roxase.access")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        request_stats.record_in_flight(1)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            status = response.status_code
        except Exception:
            status = 500
            raise
        finally:
            request_stats.record_in_flight(-1)
            request_stats.record(status)
            request_id_var.reset(token)
            logger.info("%s %s -> %d", request.method, request.url.path, status)
        return response