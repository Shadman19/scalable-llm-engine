"""Operational endpoints: health, readiness, queue depth, cost/usage."""

from fastapi import APIRouter, Request

from app.core import cost, queue
from app.core.redis_client import get_redis

router = APIRouter(tags=["admin"])


@router.get("/health")
async def health() -> dict:
    """Liveness — is the process up? Used by k8s livenessProbe."""
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict:
    """Readiness — can we actually serve? Checks Redis. Used by k8s
    readinessProbe so a pod with a dead Redis link is pulled from the LB."""
    try:
        await get_redis().ping()
        redis_ok = True
    except Exception:
        redis_ok = False
    return {"status": "ready" if redis_ok else "degraded", "redis": redis_ok}


@router.get("/v1/admin/queue")
async def queue_status() -> dict:
    """Queue depth — the key signal for autoscaling the worker tier (KEDA)."""
    return {"queue_depth": await queue.queue_depth()}


@router.get("/v1/admin/usage")
async def usage(tenant: str = "default", day: str | None = None) -> dict:
    """Live spend + token counters for a tenant/day."""
    return {"tenant": tenant, "usage": await cost.get_usage(tenant, day)}
