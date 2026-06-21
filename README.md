# Scalable LLM Engine

### 🔗 [Try the live demo →](https://shadman19.github.io/scalable-llm-engine/)

Paste a technician's messy work-order notes and watch the engine turn them into a clean, structured summary — no setup required.

![CI](https://github.com/Shadman19/scalable-llm-engine/actions/workflows/ci.yml/badge.svg)

## Demo

> **▶️ Watch the 60-second demo:** [LINK_HERE]

The engine running locally — a technician's raw work-order notes turned into a
clean, structured client summary via the MiniMax-backed API, served through the
auto-generated OpenAPI UI.

<!-- Optional: add a screenshot of the /docs page or smoke-test output:
![API docs](docs/images/demo.png)
-->

A production-grade **LLM gateway** built around the MiniMax API, designed to scale
on Kubernetes. It demonstrates a clean path from a fast MVP to a horizontally
scalable, cost-tracked, autoscaling service — and a planned, low-friction
migration to self-hosted GPU inference.

Built as a reference implementation for an **IT field-service marketplace**
(technician ↔ work-order platform). The included use case turns a technician's
raw work-order notes into a clean, structured client summary.

> **Scope of this repository:** Part 1 (MiniMax API MVP), Part 6 (scalable
> deployment — Docker / Kubernetes / Redis / queue), Part 7 (self-hosted model
> feasibility + GPU sizing). The RAG, prompt-management, and full backend-routing
> components are separate workstreams.

---

## What's inside

- **FastAPI gateway** with sync + async endpoints, auto-generated OpenAPI docs.
- **MiniMax provider** — OpenAI-compatible HTTP client with retries, backoff,
  and logical→concrete model routing (`fast` / `smart`).
- **Redis** doing triple duty: response **cache**, job **queue**, and atomic
  **cost counters**.
- **Background worker** that drains the queue, scaled independently of the API.
- **Docker + docker-compose** for one-command local dev.
- **Kubernetes manifests** with health probes, HPA (API) and KEDA queue-depth
  autoscaling (workers), ingress + TLS.
- **Tests** (no infra required) + smoke test + load test scripts.
- **Three design docs** covering Parts 1, 6, and 7.

---

## Architecture at a glance

```
client ─▶ Ingress ─▶ API (FastAPI, autoscaled)
                       │  ├── sync:  cache → MiniMax → cost → cache → respond
                       │  └── async: enqueue → 202 {job_id}
                       ▼
                     Redis  (cache + queue + cost)
                       ▲
                     Worker tier (autoscaled on queue depth) ─▶ MiniMax API
```

Full details in [`docs/architecture.md`](docs/architecture.md).

---

## Quick start (from scratch)

### Prerequisites

- **Docker** + **Docker Compose** (easiest path), OR Python 3.12 + a local Redis.
- A **MiniMax API key** — sign up at <https://platform.minimax.io>, then
  User Center → Interface Key. Copy the key.

### Option A — Docker Compose (recommended)

```bash
# 1. Get the code and enter it
cd scalable-llm-engine

# 2. Create your env file and paste your key
cp .env.example .env
#    edit .env and set MINIMAX_API_KEY=...

# 3. Start everything (Redis + API + worker)
docker compose up --build

# 4. In another terminal, exercise every endpoint
bash scripts/smoke_test.sh
```

- API: <http://localhost:8000>
- Interactive docs: <http://localhost:8000/docs>
- Scale workers locally: `docker compose up --scale worker=3`

### Option B — Run locally without Docker

```bash
# 1. Start a Redis (any way you like), e.g.:
docker run -p 6379:6379 redis:7-alpine

# 2. Install deps
pip install -r requirements-dev.txt

# 3. Configure
cp .env.example .env
#    set MINIMAX_API_KEY=... and REDIS_URL=redis://localhost:6379/0

# 4. Run the API and a worker in two terminals
make run        # terminal 1  (uvicorn, auto-reload)
make worker     # terminal 2
```

---

## Using the API

### Synchronous chat

```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Hello"}],"model":"smart","max_tokens":64}'
```

`model` accepts a logical name (`fast`, `smart`) or a concrete MiniMax id.

### Work-order summary (field-service marketplace use case)

```bash
curl -X POST http://localhost:8000/v1/usecases/work-order-summary \
  -H "Content-Type: application/json" \
  -d '{
        "work_order_id": "WO-10231",
        "site": "Retail Store #482, Dallas TX",
        "skill": "POS / Network",
        "raw_notes": "Replaced faulty switch in IDF closet. Two registers were offline, both back up. Tested all 6 lanes, all green. Recommend UPS replacement next visit."
      }'
```

Add `"async_mode": true` to queue it and get a `job_id` back instead.

### Async + polling

```bash
# enqueue
curl -X POST http://localhost:8000/v1/chat/async \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"summarize ..."}],"model":"fast"}'
# -> {"job_id":"...","status":"queued"}

# poll
curl http://localhost:8000/v1/jobs/<job_id>
```

### Live cost & usage

```bash
curl "http://localhost:8000/v1/admin/usage?tenant=work-order-summary"
curl "http://localhost:8000/v1/admin/queue"
```

---

## Tests

```bash
make test        # 8 unit tests, no Redis/network needed
```

The unit tests cover model routing, cost math, response parsing, and schema
defaults — the pure logic — so they run anywhere.

---

## Deploying to Kubernetes

See [`scalable-deployment.md`](docs/06-scalable-deployment.md) for the
full walkthrough. Short version:

```bash
# build & push your image first, then update the image: field in k8s/04 & k8s/06
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/01-configmap.yaml
kubectl -n llm-engine create secret generic llm-engine-secrets \
  --from-literal=MINIMAX_API_KEY=your_real_key
kubectl apply -f k8s/03-redis.yaml
kubectl apply -f k8s/04-api-deployment.yaml -f k8s/05-api-service.yaml
kubectl apply -f k8s/06-worker-deployment.yaml
kubectl apply -f k8s/07-api-hpa.yaml
kubectl apply -f k8s/08-worker-hpa.yaml      # requires KEDA
kubectl apply -f k8s/09-ingress.yaml         # adjust host + TLS
```

---

## Documentation

| Doc | Covers |
|-----|--------|
| [`docs/mvp-setup.md`](docs/01-mvp-setup.md) | **Part 1** — MiniMax API MVP, gateway rationale, model routing |
| [`docs/scalable-deployment.md`](docs/06-scalable-deployment.md) | **Part 6** — Docker, Kubernetes, Redis, queue, autoscaling |
| [`docs/self-hosted-feasibility.md`](docs/07-self-hosted-feasibility.md) | **Part 7** — self-hosting break-even, GPU sizing, vLLM, compliance |
| [`docs/architecture.md`](docs/architecture.md) | Codebase map + design principles |

---

## Project layout

```
scalable-llm-engine/
├── app/              FastAPI app, provider, core (cache/queue/cost), worker
├── k8s/              Kubernetes manifests (numbered, apply in order)
├── docs/             Parts 1 / 6 / 7 + architecture
├── scripts/          smoke_test.sh, load_test.py
├── tests/            unit tests (no infra)
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── requirements.txt
└── .env.example
```

---

## Configuration reference

All via environment variables (see `.env.example`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `MINIMAX_API_KEY` | — | **required**; from the MiniMax console |
| `MINIMAX_BASE_URL` | `https://api.minimax.io/v1` | OpenAI-compatible endpoint |
| `MINIMAX_DEFAULT_MODEL` | `MiniMax-M2.5` | fallback concrete model |
| `REDIS_URL` | `redis://redis:6379/0` | cache + queue + counters |
| `CACHE_ENABLED` | `true` | toggle the response cache |
| `CACHE_TTL_SECONDS` | `3600` | cache entry lifetime |
| `ENVIRONMENT` | `development` | `production` in prod |
| `LOG_LEVEL` | `INFO` | log verbosity |

---

## Notes & honesty

- Model names and pricing in `app/core/cost.py` are **approximate** — confirm
  against your MiniMax billing page before relying on the cost figures.
- The single-pod Redis and list-based queue are deliberate MVP choices; the docs
  call out the production upgrades (managed Redis/HA, Redis Streams or a broker
  for at-least-once delivery, semantic caching).
- This is a reference architecture meant to be read and adapted, not a
  drop-in production system for any specific company.
