"""Request / response schemas shared across routers."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]
    # Logical model name. The provider maps this to a concrete MiniMax model.
    # Use "fast" for cheap/high-volume tasks, "smart" for complex reasoning.
    model: str = Field(default="smart")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1, le=131072)
    # Cache key namespace, useful to separate tenants / use cases.
    tenant: str = Field(default="default")
    # Skip the cache for this request (e.g. non-deterministic generations).
    no_cache: bool = Field(default=False)


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    content: str
    model: str
    usage: Usage
    cached: bool = False
    cost_usd: float = 0.0
    latency_ms: int = 0


class JobAccepted(BaseModel):
    job_id: str
    status: Literal["queued"] = "queued"


class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "processing", "done", "error"]
    result: Optional[ChatResponse] = None
    error: Optional[str] = None


# ---- Field-service marketplace use case payloads ----


class WorkOrderSummaryRequest(BaseModel):
    """Summarize a technician's raw work-order notes into a clean summary."""

    work_order_id: str
    raw_notes: str
    # Optional structured context the model can lean on.
    site: Optional[str] = None
    skill: Optional[str] = None
    async_mode: bool = Field(
        default=False, description="Queue the job instead of waiting inline."
    )
