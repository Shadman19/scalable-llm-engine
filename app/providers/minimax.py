"""
MiniMax provider — calls the OpenAI-compatible Chat Completions endpoint.

MiniMax exposes an OpenAI-compatible API at https://api.minimax.io/v1, so we
use plain HTTP via httpx (no extra SDK lock-in). Auth is a bearer token.

Model routing
-------------
Callers send a *logical* model name ("fast" / "smart"). We map that to a
concrete MiniMax model here. This is the seam that lets you:
  - send high-volume, simple tasks (classification, short summaries) to a
    cheaper/faster model, and
  - send complex reasoning (multi-step support answers) to a stronger model,
  - and later route "fast" to a self-hosted vLLM model with zero caller changes.
"""

import asyncio
import logging

import httpx

from app.config import get_settings
from app.providers.base import CompletionResult, LLMProvider
from app.schemas import Message

logger = logging.getLogger(__name__)

# Logical name -> concrete MiniMax model id.
# Confirm exact model ids/availability on platform.minimax.io.
MODEL_ROUTES = {
    "fast": "MiniMax-M2.5",
    "smart": "MiniMax-M3",
    "default": "MiniMax-M2.5",
}


def resolve_model(logical_or_concrete: str, default_concrete: str) -> str:
    if logical_or_concrete in MODEL_ROUTES:
        return MODEL_ROUTES[logical_or_concrete]
    # Allow callers to pass a concrete model id directly.
    return logical_or_concrete or default_concrete


class MiniMaxProvider(LLMProvider):
    def __init__(self) -> None:
        settings = get_settings()
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.minimax_base_url,
            timeout=settings.request_timeout_seconds,
            headers={
                "Authorization": f"Bearer {settings.minimax_api_key}",
                "Content-Type": "application/json",
            },
        )

    async def complete(
        self,
        messages,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> CompletionResult:
        concrete = resolve_model(model, self._settings.minimax_default_model)
        body = {
            "model": concrete,
            "messages": [
                {"role": m.role, "content": m.content}
                if isinstance(m, Message)
                else m
                for m in messages
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        last_exc: Exception | None = None
        for attempt in range(1, self._settings.max_retries + 1):
            try:
                resp = await self._client.post("/chat/completions", json=body)
                if resp.status_code == 429 or resp.status_code >= 500:
                    # Transient: back off and retry.
                    raise httpx.HTTPStatusError(
                        f"transient {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                resp.raise_for_status()
                data = resp.json()
                return self._parse(data, concrete)
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                if attempt == self._settings.max_retries:
                    break
                backoff = min(2 ** attempt * 0.5, 8.0)
                logger.warning(
                    "minimax call failed, retrying",
                    extra={"ctx_attempt": attempt, "ctx_backoff_s": backoff},
                )
                await asyncio.sleep(backoff)

        raise RuntimeError(f"MiniMax request failed after retries: {last_exc}")

    @staticmethod
    def _parse(data: dict, concrete_model: str) -> CompletionResult:
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        # MiniMax can return reasoning + text; if content is a list, join text.
        if isinstance(content, list):
            content = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        usage = data.get("usage") or {}
        return CompletionResult(
            content=content,
            model=data.get("model", concrete_model),
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
        )

    async def aclose(self) -> None:
        await self._client.aclose()
