"""Rate limiting V1.

A fixed-window limiter keyed on (client identity + scope) using Redis
(INCR + EXPIRE + PEXPIRE) which is atomic within a single key. Enforced only on
routes that opt in via the dependency and only when Redis is reachable; if Redis
is briefly unavailable the limiter degrades open (logs a warning) so a cache
outage never blocks legitimate traffic and never breaks local/dev/test runs.

Exceeding the window returns HTTP 429.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, Request

from app.core.cache import get_redis
from app.core.config import settings

logger = logging.getLogger("roxase.ratelimit")


class RateLimiter:
    """Redis-backed fixed-window rate limiter for a configurable scope."""

    def __init__(self, limit: int, window_seconds: int, scope: str = "api"):
        self.limit = limit
        self.window = window_seconds
        self.scope = scope

    def _key(self, identity: str) -> str:
        return f"rl:{self.scope}:{identity}"

    async def __call__(self, request: Request) -> None:
        if not settings.rate_limit_enabled:
            return
        identity = self._identity(request)
        try:
            redis = get_redis()
            key = self._key(identity)
            current = await redis.incr(key)
            if current == 1:
                await redis.expire(key, self.window)
            if current > self.limit:
                raise HTTPException(status_code=429, detail="rate limit exceeded")
        except HTTPException:
            raise
        except Exception:  # pragma: no cover - Redis outage degrades open
            logger.warning("rate limiter unavailable (Redis); skipping enforcement")

    def _identity(self, request: Request) -> str:
        user = getattr(request.state, "user", None)
        if user is not None:
            return str(getattr(user, "id", "anon"))
        return request.client.host if request.client else "unknown"


# Default per-process limit for the API.
default_limiter = RateLimiter(
    limit=settings.rate_limit_burst,
    window_seconds=settings.rate_limit_window,
    scope="default",
)