"""Single shared async Redis connection pool.

Used by the cache, the queue, and the cost tracker. Redis is the cheapest
way to get a shared cache + a durable job queue + atomic counters without
standing up extra infrastructure for an MVP.
"""

from redis.asyncio import Redis

from app.config import get_settings

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = Redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            health_check_interval=30,
        )
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
