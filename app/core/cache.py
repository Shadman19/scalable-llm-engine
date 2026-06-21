"""Exact-match response cache.

Keying strategy: hash of (tenant, model, temperature, messages). Identical
requests (e.g. the same FAQ asked repeatedly, or a re-tried summarization)
are served from Redis instead of paying for another API call. This is the
single biggest cost lever for a high-volume marketplace where many requests
repeat.

For semantic (fuzzy) caching you would add an embedding lookup in front of
this — noted in docs/06-scalable-deployment.md as a next step.
"""

import hashlib
import json
from typing import Optional

from app.config import get_settings
from app.core.redis_client import get_redis


def _cache_key(tenant: str, model: str, temperature: float, messages: list) -> str:
    raw = json.dumps(
        {"t": tenant, "m": model, "temp": temperature, "msgs": messages},
        sort_keys=True,
        ensure_ascii=False,
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"cache:{tenant}:{digest}"


async def get_cached(
    tenant: str, model: str, temperature: float, messages: list
) -> Optional[dict]:
    settings = get_settings()
    if not settings.cache_enabled:
        return None
    key = _cache_key(tenant, model, temperature, messages)
    raw = await get_redis().get(key)
    return json.loads(raw) if raw else None


async def set_cached(
    tenant: str,
    model: str,
    temperature: float,
    messages: list,
    payload: dict,
) -> None:
    settings = get_settings()
    if not settings.cache_enabled:
        return
    key = _cache_key(tenant, model, temperature, messages)
    await get_redis().set(
        key, json.dumps(payload, ensure_ascii=False), ex=settings.cache_ttl_seconds
    )
