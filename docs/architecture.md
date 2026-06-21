# Architecture Overview

A one-page map of the codebase so a reviewer can navigate it in two minutes.

## Request paths

**Synchronous** (interactive): client → `POST /v1/chat` →
`run_chat()` → [cache hit? return] → MiniMax provider → record cost → cache →
return.

**Asynchronous** (bulk): client → `POST /v1/chat/async` → enqueue in Redis →
`202 {job_id}`. A worker `BLPOP`s the job → `run_chat()` (same path) → writes
result under `job:<id>`. Client polls `GET /v1/jobs/{job_id}`.

Both paths share `run_chat()`, so caching, retries, and cost accounting are
identical regardless of entry point.

## Module map

```
app/
├── main.py                 FastAPI app, lifespan, middleware, router wiring
├── config.py               env-driven settings (no hardcoded secrets)
├── schemas.py              pydantic request/response models
├── worker.py               background queue consumer (runs as its own process)
├── providers/
│   ├── base.py             LLMProvider interface (the swap seam)
│   └── minimax.py          MiniMax client: HTTP, retries, model routing
├── core/
│   ├── redis_client.py     shared async Redis pool
│   ├── cache.py            exact-match response cache
│   ├── queue.py            Redis list-based job queue
│   ├── cost.py             token + USD counters (atomic), pricing table
│   ├── service.py          run_chat(): cache → provider → cost orchestration
│   └── logging_config.py   structured JSON logging
└── routers/
    ├── chat.py             /v1/chat, /v1/chat/async
    ├── jobs.py             /v1/jobs/{id}
    ├── usecases.py         /v1/usecases/work-order-summary (field-service marketplace task)
    └── admin.py            /health, /ready, /v1/admin/queue, /v1/admin/usage
```

## Design principles

1. **Vendor behind an interface.** Nothing outside `providers/` knows MiniMax
   exists. Self-hosting later (Part 7) is a new subclass + a config change.
2. **One orchestration path.** Sync and async both call `run_chat()`.
3. **Redis does three jobs** — cache, queue, cost counters — so the MVP needs no
   extra infrastructure.
4. **Two scalable tiers.** API scales on load; workers scale on queue depth.
5. **Cost is first-class.** Every call is priced and counted at request time.

## Where the documented parts live

- **Part 1 — MVP setup:** `docs/01-mvp-setup.md`
- **Part 6 — Scalable deployment:** `docs/06-scalable-deployment.md` + `k8s/`
- **Part 7 — Self-hosted feasibility:** `docs/07-self-hosted-feasibility.md`
