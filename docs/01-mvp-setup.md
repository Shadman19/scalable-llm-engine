# Part 1 — MiniMax API-based MVP Setup

The goal of the MVP is to get a **working, observable LLM endpoint** in front of
the product as fast as possible, without committing to GPU infrastructure. We do
that by treating MiniMax's hosted API as the model backend and putting a thin,
swappable gateway in front of it.

## Why a gateway instead of calling MiniMax directly

If every service in the product calls the MiniMax SDK directly, you get:

- the API key scattered across many codebases,
- no shared cache (you pay for the same answer repeatedly),
- no central cost tracking,
- and a painful migration the day you want to self-host (Part 7).

A gateway solves all four. The product calls **our** endpoint; we decide which
model runs, whether to serve from cache, and how to account for spend. Swapping
MiniMax for a self-hosted model later is a one-file change.

## MiniMax facts that shape the design

MiniMax exposes an **OpenAI-compatible** Chat Completions API, so we use plain
HTTP (no vendor SDK lock-in):

- Base URL: `https://api.minimax.io/v1`
- Endpoint: `POST /chat/completions`
- Auth: `Authorization: Bearer <API_KEY>` (key from the MiniMax console →
  User Center → Interface Key)
- Models (confirm current list/pricing in your console before launch):
  `MiniMax-M3` (strong reasoning, large context), `MiniMax-M2.7`, `MiniMax-M2.5`.

We map **logical** model names to concrete ones in
`app/providers/minimax.py` (`MODEL_ROUTES`):

| Logical name | Concrete model | Use for |
|--------------|----------------|---------|
| `fast`       | `MiniMax-M2.5` | high-volume, simple tasks (summaries, classification) |
| `smart`      | `MiniMax-M3`   | complex multi-step reasoning (support answers) |

Callers never hardcode a concrete model, so re-routing `fast` to a cheaper or
self-hosted model later changes nothing for them.

## What the MVP includes

- `POST /v1/chat` — synchronous completion (interactive use).
- `POST /v1/usecases/work-order-summary` — a concrete field-service marketplace task: turn a
  technician's raw notes into a structured client-facing summary.
- Exact-match **response cache** (Redis) — identical requests are free.
- **Cost tracking** — every call increments per-model, per-tenant counters.
- Automatic **retries with backoff** on 429 / 5xx from MiniMax.
- Structured JSON logs for every request.

## Run it in 3 commands

```bash
cp .env.example .env          # then paste your MINIMAX_API_KEY
docker compose up --build     # starts redis + api + worker
bash scripts/smoke_test.sh    # exercises every endpoint
```

Interactive API docs are auto-generated at `http://localhost:8000/docs`.

## Example call

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

The response is a structured summary plus token usage and the **exact USD cost**
of that call — so cost is visible from request one, not discovered on the
monthly invoice.

## MVP boundaries (intentionally deferred)

- No semantic (fuzzy) cache yet — exact-match only. Added in Part 6.
- No auth on the gateway itself — front it with your existing API gateway / mTLS
  inside the cluster for now.
- Single Redis pod — fine for the MVP, hardened in Part 6.
