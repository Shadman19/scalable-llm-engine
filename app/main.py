"""
FastAPI entrypoint.

Wires the provider into app.state at startup so a single httpx connection pool
is reused across requests (creating a client per request kills throughput).
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.config import get_settings
from app.core.logging_config import configure_logging
from app.core.redis_client import close_redis
from app.providers.minimax import MiniMaxProvider
from app.routers import admin, chat, jobs, usecases

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.provider = MiniMaxProvider()
    logger.info("startup complete", extra={"ctx_env": settings.environment})
    try:
        yield
    finally:
        await app.state.provider.aclose()
        await close_redis()
        logger.info("shutdown complete")


app = FastAPI(
    title="Scalable LLM Engine",
    version="0.1.0",
    description="Scalable LLM gateway: MiniMax MVP, Redis cache/queue, k8s-ready.",
    lifespan=lifespan,
)

app.include_router(admin.router)
app.include_router(chat.router)
app.include_router(jobs.router)
app.include_router(usecases.router)


@app.middleware("http")
async def add_latency_header(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    response.headers["X-Process-Time-Ms"] = str(elapsed_ms)
    logger.info(
        "request",
        extra={
            "ctx_method": request.method,
            "ctx_path": request.url.path,
            "ctx_status": response.status_code,
            "ctx_latency_ms": elapsed_ms,
        },
    )
    return response


@app.get("/", tags=["admin"])
async def root() -> dict:
    return {
        "service": settings.app_name,
        "version": "0.1.0",
        "docs": "/docs",
    }
