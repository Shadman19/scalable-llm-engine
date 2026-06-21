"""Chat endpoints: synchronous (inline) and asynchronous (queued)."""

from fastapi import APIRouter, HTTPException, Request

from app.config import get_settings
from app.core import queue
from app.core.service import run_chat
from app.schemas import ChatRequest, ChatResponse, JobAccepted

router = APIRouter(prefix="/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request) -> ChatResponse:
    """Synchronous completion. Use for interactive, latency-sensitive calls
    (support chat, single work-order lookups)."""
    settings = get_settings()
    total_chars = sum(len(m.content) for m in req.messages)
    if total_chars > settings.max_prompt_chars:
        raise HTTPException(status_code=413, detail="prompt too large")

    provider = request.app.state.provider
    return await run_chat(
        provider=provider,
        messages=req.messages,
        model=req.model,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
        tenant=req.tenant,
        no_cache=req.no_cache,
    )


@router.post("/chat/async", response_model=JobAccepted, status_code=202)
async def chat_async(req: ChatRequest) -> JobAccepted:
    """Queue a completion and return immediately. Use for bulk / batch work
    where you do not need the answer in-band (overnight summarization, scoring).
    Poll GET /v1/jobs/{job_id} for the result."""
    job_id = await queue.enqueue({"type": "chat", "request": req.model_dump()})
    return JobAccepted(job_id=job_id)
