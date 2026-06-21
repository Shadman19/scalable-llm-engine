"""
Orchestration: cache -> provider -> cost tracking.

Both the synchronous API path and the async worker call run_chat(), so the
caching, retry, and cost-accounting behaviour is identical no matter how a
request enters the system.
"""

import time
from typing import List

from app.core import cache, cost
from app.providers.base import LLMProvider
from app.providers.minimax import resolve_model
from app.config import get_settings
from app.schemas import ChatResponse, Message, Usage


async def run_chat(
    provider: LLMProvider,
    messages: List[Message],
    model: str,
    temperature: float,
    max_tokens: int,
    tenant: str,
    no_cache: bool = False,
) -> ChatResponse:
    settings = get_settings()
    started = time.perf_counter()

    serialized = [{"role": m.role, "content": m.content} for m in messages]

    # 1) Cache lookup (exact match).
    if not no_cache:
        hit = await cache.get_cached(tenant, model, temperature, serialized)
        if hit:
            hit["cached"] = True
            hit["latency_ms"] = int((time.perf_counter() - started) * 1000)
            return ChatResponse(**hit)

    # 2) Call the model.
    result = await provider.complete(messages, model, temperature, max_tokens)

    # 3) Cost accounting (atomic counters in Redis).
    concrete = result.model or resolve_model(model, settings.minimax_default_model)
    cost_usd = cost.estimate_cost(
        concrete, result.prompt_tokens, result.completion_tokens
    )
    await cost.record_usage(
        tenant, concrete, result.prompt_tokens, result.completion_tokens, cost_usd
    )

    response = ChatResponse(
        content=result.content,
        model=concrete,
        usage=Usage(
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.prompt_tokens + result.completion_tokens,
        ),
        cached=False,
        cost_usd=cost_usd,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )

    # 4) Populate cache.
    if not no_cache:
        await cache.set_cached(
            tenant, model, temperature, serialized, response.model_dump()
        )

    return response
