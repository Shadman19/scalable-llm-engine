"""Per-model, per-tenant cost + token tracking via Redis hash counters.

Every completion increments atomic counters so you get live spend visibility
without a separate analytics pipeline. Pricing below is approximate and must
be confirmed against your MiniMax billing page — keep it in config, not code,
in a real deployment.

Prices are USD per 1,000,000 tokens.
"""

from datetime import datetime, timezone

from app.core.redis_client import get_redis

# Approximate published rates (USD / 1M tokens). VERIFY on your billing page.
PRICING = {
    "MiniMax-M3": {"input": 0.70, "output": 2.80},
    "MiniMax-M2.7": {"input": 0.30, "output": 1.20},
    "MiniMax-M2.5": {"input": 0.30, "output": 1.20},
    "MiniMax-M2": {"input": 0.30, "output": 1.20},
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    rates = PRICING.get(model, {"input": 0.30, "output": 1.20})
    cost = (
        prompt_tokens / 1_000_000 * rates["input"]
        + completion_tokens / 1_000_000 * rates["output"]
    )
    return round(cost, 6)


async def record_usage(
    tenant: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
) -> None:
    r = get_redis()
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"usage:{day}:{tenant}"
    # Atomic, race-free increments.
    pipe = r.pipeline()
    pipe.hincrby(key, f"{model}:requests", 1)
    pipe.hincrby(key, f"{model}:prompt_tokens", prompt_tokens)
    pipe.hincrby(key, f"{model}:completion_tokens", completion_tokens)
    pipe.hincrbyfloat(key, f"{model}:cost_usd", cost_usd)
    pipe.expire(key, 60 * 60 * 24 * 90)  # retain 90 days
    await pipe.execute()


async def get_usage(tenant: str, day: str | None = None) -> dict:
    day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"usage:{day}:{tenant}"
    return await get_redis().hgetall(key)
