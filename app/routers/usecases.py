"""
Field-service marketplace use-case endpoints.

These wrap the generic chat engine with task-specific prompts so the rest of
the product calls a clean business endpoint (e.g. /v1/usecases/work-order-summary)
instead of hand-rolling prompts everywhere. Prompt text lives here, versioned
in git — this is the "prompt management" seam.
"""

from fastapi import APIRouter, Request

from app.core import queue
from app.core.service import run_chat
from app.schemas import (
    ChatResponse,
    JobAccepted,
    Message,
    WorkOrderSummaryRequest,
)

router = APIRouter(prefix="/v1/usecases", tags=["use-cases"])

WORK_ORDER_SUMMARY_SYSTEM = (
    "You are an assistant for an IT field-service marketplace. Given a "
    "technician's raw work-order notes, produce a concise, professional "
    "summary for the client. Use this exact structure:\n"
    "- Work performed: <1-2 sentences>\n"
    "- Issues found: <bullet list or 'None reported'>\n"
    "- Resolution status: <Completed | Partial | Escalation needed>\n"
    "- Follow-up required: <yes/no + what>\n"
    "Be factual. Do not invent details that are not in the notes."
)


def _build_messages(req: WorkOrderSummaryRequest) -> list[Message]:
    context_lines = [f"Work order: {req.work_order_id}"]
    if req.site:
        context_lines.append(f"Site: {req.site}")
    if req.skill:
        context_lines.append(f"Skill: {req.skill}")
    context = "\n".join(context_lines)
    return [
        Message(role="system", content=WORK_ORDER_SUMMARY_SYSTEM),
        Message(
            role="user",
            content=f"{context}\n\nRaw technician notes:\n{req.raw_notes}",
        ),
    ]


@router.post("/work-order-summary")
async def work_order_summary(req: WorkOrderSummaryRequest, request: Request):
    """Summarize technician notes. Set async_mode=true for bulk processing."""
    messages = _build_messages(req)

    if req.async_mode:
        job_id = await queue.enqueue(
            {
                "type": "chat",
                "request": {
                    "messages": [m.model_dump() for m in messages],
                    # Summaries are cheap/repetitive -> route to the fast model.
                    "model": "fast",
                    "temperature": 0.2,
                    "max_tokens": 512,
                    "tenant": "work-order-summary",
                    "no_cache": False,
                },
            }
        )
        return JobAccepted(job_id=job_id)

    provider = request.app.state.provider
    result: ChatResponse = await run_chat(
        provider=provider,
        messages=messages,
        model="fast",
        temperature=0.2,
        max_tokens=512,
        tenant="work-order-summary",
    )
    return result
