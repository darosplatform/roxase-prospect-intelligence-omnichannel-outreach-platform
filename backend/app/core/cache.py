"""Redis cache client (used for readiness checks and rate limiting)."""

from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import settings

redis_client: Redis | None = None


def get_redis() -> Redis:
    global redis_client
    if redis_client is None:
        redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    return redis_client


async def close_redis() -> None:
    global redis_client
    if redis_client is not None:
        await redis_client.aclose()
        redis_client = None