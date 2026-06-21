"""A minimal but durable Redis list-based job queue.

Why a queue at all? For high-volume, latency-tolerant work (bulk work-order
summarization overnight, batch quality scoring) you do NOT want to hold an
HTTP connection open. The API enqueues a job and returns instantly; a pool of
workers (scaled independently) drains the queue. This decouples request spikes
from model throughput and lets you autoscale the two tiers separately.

Production note: for at-least-once delivery with retries and dead-letter
queues, graduate to Redis Streams (XADD/XREADGROUP) or a broker like RabbitMQ
/ SQS. This list-based version is intentionally simple for the MVP and is
called out in docs/06-scalable-deployment.md.
"""

import json
import uuid
from typing import Optional

from app.config import get_settings
from app.core.redis_client import get_redis


def _job_key(job_id: str) -> str:
    return f"job:{job_id}"


async def enqueue(payload: dict) -> str:
    settings = get_settings()
    r = get_redis()
    job_id = uuid.uuid4().hex
    job = {"job_id": job_id, "status": "queued", "payload": payload}
    pipe = r.pipeline()
    pipe.set(
        _job_key(job_id),
        json.dumps(job, ensure_ascii=False),
        ex=settings.job_result_ttl_seconds,
    )
    pipe.rpush(settings.queue_name, job_id)
    await pipe.execute()
    return job_id


async def dequeue(timeout: int) -> Optional[str]:
    """Blocking pop. Returns a job_id or None on timeout."""
    settings = get_settings()
    result = await get_redis().blpop(settings.queue_name, timeout=timeout)
    if result is None:
        return None
    _, job_id = result
    return job_id


async def get_job(job_id: str) -> Optional[dict]:
    raw = await get_redis().get(_job_key(job_id))
    return json.loads(raw) if raw else None


async def update_job(job_id: str, **fields) -> None:
    settings = get_settings()
    r = get_redis()
    job = await get_job(job_id)
    if job is None:
        return
    job.update(fields)
    await r.set(
        _job_key(job_id),
        json.dumps(job, ensure_ascii=False),
        ex=settings.job_result_ttl_seconds,
    )


async def queue_depth() -> int:
    settings = get_settings()
    return await get_redis().llen(settings.queue_name)
