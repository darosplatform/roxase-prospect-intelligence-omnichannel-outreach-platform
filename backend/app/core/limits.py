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
    """Redis-backed fixed-window rate limiter for a configurable scope.

    `fail_open` controls what happens when Redis itself is unreachable:
    True (the default) degrades open, since a cache outage should never
    block ordinary API traffic. Unauthenticated, abuse-prone endpoints
    (login, registration) pass `fail_open=False` instead — for those, a
    Redis outage removing the only brute-force guard is worse than a
    503 during the outage.
    """

    def __init__(
        self,
        limit: int,
        window_seconds: int,
        scope: str = "api",
        fail_open: bool = True,
    ):
        self.limit = limit
        self.window = window_seconds
        self.scope = scope
        self.fail_open = fail_open

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
        except Exception:  # Redis outage: degrade per fail_open policy
            if self.fail_open:
                logger.warning("rate limiter unavailable (Redis); skipping enforcement")
                return
            logger.error(
                "rate limiter unavailable (Redis); failing closed for scope=%s",
                self.scope,
            )
            raise HTTPException(
                status_code=503, detail="service temporarily unavailable"
            ) from None

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

# Unauthenticated auth entrypoints (login, registration): brute-force /
# signup-spam protection that must not silently disappear during a Redis
# outage, so it fails closed instead of open.
auth_limiter = RateLimiter(
    limit=settings.rate_limit_burst,
    window_seconds=settings.rate_limit_window,
    scope="auth",
    fail_open=False,
)