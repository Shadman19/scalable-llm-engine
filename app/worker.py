"""
Background worker.

Runs as a separate process / k8s Deployment, scaled independently of the API.
It blocks on the Redis queue, processes one job at a time, and writes the
result back. Multiple worker replicas safely share one queue (BLPOP is atomic,
so each job is handed to exactly one worker).

Run:  python -m app.worker
"""

import asyncio
import logging

from app.config import get_settings
from app.core import queue
from app.core.logging_config import configure_logging
from app.core.redis_client import close_redis
from app.core.service import run_chat
from app.providers.minimax import MiniMaxProvider
from app.schemas import ChatRequest

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("worker")


async def process_chat_job(provider, job_id: str, payload: dict) -> None:
    req = ChatRequest(**payload["request"])
    await queue.update_job(job_id, status="processing")
    try:
        response = await run_chat(
            provider=provider,
            messages=req.messages,
            model=req.model,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            tenant=req.tenant,
            no_cache=req.no_cache,
        )
        await queue.update_job(
            job_id, status="done", result=response.model_dump()
        )
        logger.info("job done", extra={"ctx_job_id": job_id})
    except Exception as exc:  # noqa: BLE001 - record and continue draining
        await queue.update_job(job_id, status="error", error=str(exc))
        logger.exception("job failed", extra={"ctx_job_id": job_id})


async def main() -> None:
    provider = MiniMaxProvider()
    logger.info("worker started", extra={"ctx_queue": settings.queue_name})
    try:
        while True:
            job_id = await queue.dequeue(timeout=settings.worker_poll_timeout)
            if job_id is None:
                continue  # idle tick; loop again
            job = await queue.get_job(job_id)
            if job is None:
                logger.warning("job vanished", extra={"ctx_job_id": job_id})
                continue
            if job["payload"].get("type") == "chat":
                await process_chat_job(provider, job_id, job["payload"])
            else:
                await queue.update_job(
                    job_id, status="error", error="unknown job type"
                )
    finally:
        await provider.aclose()
        await close_redis()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("worker stopped")
