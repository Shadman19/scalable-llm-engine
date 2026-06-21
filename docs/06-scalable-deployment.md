# Part 6 — Scalable Deployment (Docker, Kubernetes, Redis, Queue)

This part takes the MVP from "runs on my laptop" to "survives traffic spikes in
production." The core idea is **two independently scalable tiers** sharing one
Redis, plus autoscaling driven by the right signal for each tier.

## Architecture

```
                       ┌──────────────────────────────┐
   client ──HTTPS──▶   │ Ingress (nginx) + TLS        │
                       └──────────────┬───────────────┘
                                      │
                          ┌───────────▼───────────┐
                          │  API tier (FastAPI)    │  HPA on CPU/RPS
                          │  Deployment: llm-api   │  2 → 10 replicas
                          └─────┬─────────────┬────┘
                  sync path     │             │  async path
              (cache + model)   │             │  enqueue job
                                │             ▼
                                │      ┌──────────────┐
                                │      │    Redis     │  cache + queue + cost
                                │      │  (list/keys) │
                                │      └──────┬───────┘
                                │             │ BLPOP
                                │   ┌─────────▼──────────┐
                                │   │ Worker tier        │  KEDA on queue depth
                                │   │ Deployment:        │  1 → 20 replicas
                                │   │ llm-worker         │  (scale-to-1 idle)
                                │   └─────────┬──────────┘
                                │             │
                                ▼             ▼
                          ┌──────────────────────────┐
                          │  MiniMax API (or vLLM,    │
                          │  Part 7 — same interface) │
                          └──────────────────────────┘
```

## Why two tiers

The **API tier** is I/O-bound and latency-sensitive: it answers interactive
requests and mostly waits on the model. Scale it on request load.

The **worker tier** is throughput-bound: it drains bulk/batch jobs (overnight
work-order summarization, quality scoring). Its limit is model throughput, not
HTTP concurrency. Scale it on **queue depth**.

Coupling these into one process would mean a flood of batch jobs starves
interactive traffic, and you'd be forced to scale both together. Splitting them
lets a 10,000-job overnight batch spin up 20 workers while the API tier stays
small.

## The queue: why and how

For latency-tolerant work the API does **not** hold an HTTP connection open. It
calls `POST /v1/chat/async`, gets a `job_id` back instantly, and the client
polls `GET /v1/jobs/{job_id}`. Internally this is a Redis list:

- `RPUSH llm:jobs <job_id>` to enqueue,
- `BLPOP llm:jobs` in each worker (atomic — exactly one worker gets each job),
- job state + result stored under `job:<id>` with a TTL.

This decouples request spikes from model throughput: bursts pile up in the
queue instead of timing out, and workers chew through them at a steady rate.

**Production upgrade path:** a plain list gives at-most-once-ish semantics (if a
worker crashes mid-job the job is lost). For at-least-once delivery with retries
and a dead-letter queue, move to **Redis Streams** (`XADD` / `XREADGROUP` /
`XACK`) or a dedicated broker (RabbitMQ, AWS SQS). The `app/core/queue.py`
interface is small on purpose so this swap is contained.

## Redis: three jobs in one component

1. **Cache** — exact-match response cache keyed on a hash of
   `(tenant, model, temperature, messages)`. This is the **single biggest cost
   lever** on a marketplace where the same FAQ / summary recurs constantly.
2. **Queue** — the job list above.
3. **Cost counters** — atomic `HINCRBY` / `HINCRBYFLOAT` per model/tenant/day,
   so live spend is queryable at `GET /v1/admin/usage` without a separate
   analytics pipeline.

**Production hardening:** the single Redis pod in `k8s/03-redis.yaml` is an MVP
convenience and a single point of failure. Replace it with managed Redis
(AWS ElastiCache / GCP Memorystore) or a Redis Operator with persistence + HA.

### Next cost lever: semantic cache

Exact-match catches identical requests. A **semantic cache** catches *similar*
ones: embed the prompt, look up nearest neighbours in a vector store, and reuse
an answer if similarity is above a threshold. That sits in front of the current
cache in `app/core/cache.py` and is the natural follow-up once exact-match hit
rates plateau.

## Containers

One image, two commands. The `Dockerfile` builds a single slim image; the API
runs `uvicorn app.main:app`, the worker overrides the command with
`python -m app.worker`. Same code, same config, different entrypoint — so the
two tiers can never drift apart.

`docker compose up --scale worker=3` runs the whole stack locally with three
workers, which is the easiest way to see the queue and autoscaling logic behave
before touching a cluster.

## Kubernetes

Apply in order (numbered for that reason):

```bash
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/01-configmap.yaml
kubectl -n llm-engine create secret generic llm-engine-secrets \
  --from-literal=MINIMAX_API_KEY=your_real_key
kubectl apply -f k8s/03-redis.yaml
kubectl apply -f k8s/04-api-deployment.yaml
kubectl apply -f k8s/05-api-service.yaml
kubectl apply -f k8s/06-worker-deployment.yaml
kubectl apply -f k8s/07-api-hpa.yaml
kubectl apply -f k8s/08-worker-hpa.yaml   # needs KEDA installed
kubectl apply -f k8s/09-ingress.yaml
```

Key resilience pieces baked into the manifests:

- **Probes** — `livenessProbe` restarts wedged pods; `readinessProbe` (which
  checks Redis via `/ready`) keeps traffic off a pod that cannot serve, so a
  Redis blip doesn't return errors to users.
- **Resource requests/limits** — let the scheduler bin-pack and let HPAs read
  meaningful utilization.
- **Non-root container** — the image runs as UID 10001.
- **Secrets vs config** — the API key lives in a `Secret`, everything else in a
  `ConfigMap`. Use an external secret manager in real production.

## Autoscaling signals (the important bit)

| Tier   | Scaler | Signal | Why |
|--------|--------|--------|-----|
| API    | HPA    | CPU (proxy for RPS) | tracks interactive load |
| Worker | KEDA   | Redis queue depth | tracks backlog directly; can scale to 1 when idle |

Scaling workers on CPU would be wrong — a worker waiting on the model API is
idle on CPU even while 5,000 jobs wait in the queue. KEDA reads the list length
and scales on the thing that actually matters.

## What to monitor

- **TTFT** (time to first token) and **TPOT** (time per output token) — user-felt
  latency.
- **Queue depth** and **job age** — is the worker tier keeping up?
- **Cache hit rate** — directly proportional to cost saved.
- **Cost per tenant/day** — already exposed at `/v1/admin/usage`.
- **5xx / retry rate from MiniMax** — upstream health.

Wire the JSON logs into your aggregator and scrape these as metrics
(Prometheus + Grafana is the common pairing).
