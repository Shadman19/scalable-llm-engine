# Part 7 — Self-Hosted Model Feasibility & GPU Requirements

This part answers one question: **when does it make sense to stop paying per
token and run our own model on GPUs instead?** It covers the decision logic, the
GPU sizing math, the inference engine choice, and how the gateway makes the
switch nearly free of code changes.

> All prices and per-GPU numbers below are **approximate** and change often.
> Treat them as a framework, not gospel — benchmark on your real traffic and
> confirm current cloud pricing before committing budget.

## 1. When self-hosting wins (the break-even logic)

A hosted API is **pay-per-token**: cost scales linearly with usage and is near
zero when idle. Self-hosting is **pay-per-GPU-hour**: a large fixed cost whether
the GPU is busy or idle, but with effectively zero marginal cost per token.

So the trade-off is **utilization**:

- **Low or spiky volume** → hosted API wins. You'd be paying for idle GPUs.
- **High, sustained volume** → self-hosting wins once the fixed GPU bill is
  cheaper than the equivalent per-token spend.

### Worked break-even example (illustrative)

Suppose a high-volume task (work-order summarization) runs at a steady **rate**
and you're comparing one `MiniMax-M2.5`-class API against one self-hosted
open model on a single GPU.

- Hosted: ~`$0.30 / 1M input` + `$1.20 / 1M output` (verify current rates).
- Self-hosted: one H100 ≈ **$2–4/hour** on-demand (cheaper reserved / spot),
  i.e. roughly **$1,500–2,900/month** running 24/7.

A single well-tuned GPU serving a small open model with continuous batching can
push **millions of tokens per hour**. The crossover is roughly:

```
monthly_api_spend  >  monthly_gpu_cost  +  ops_overhead
```

If the workload's projected API bill clears the GPU-plus-engineering cost with
margin, self-hosting pays off. Below that line, **stay on the API** — the
engineering and on-call cost of running GPUs is real and easy to underestimate.

**Pragmatic recommendation:** keep the hosted API for complex reasoning
(`smart` route) and for everything low-volume, and only self-host the **one or
two highest-volume, simplest tasks** (the `fast` route). This is the hybrid
strategy the gateway is built for.

## 2. GPU sizing math

Total VRAM needed = **model weights** + **KV cache** + **overhead** (activations,
CUDA context, fragmentation; budget ~10–20%).

### Model weights

```
weights_GB ≈ params_billion × bytes_per_param
```

| Precision | Bytes/param | 8B model | 70B model |
|-----------|-------------|----------|-----------|
| FP16/BF16 | 2.0         | ~16 GB   | ~140 GB   |
| FP8 / INT8| 1.0         | ~8 GB    | ~70 GB    |
| INT4 (AWQ/GPTQ) | 0.5   | ~4 GB    | ~35 GB    |

Quantization is the biggest single lever for fitting a model on fewer GPUs.
INT8/FP8 are usually near-lossless for these tasks; INT4 trades a little quality
for big memory savings — **benchmark quality on your task before shipping it.**

### KV cache (the part people forget)

Each concurrent request stores a key/value tensor for every token in its
context. Rough per-token cost:

```
kv_bytes_per_token ≈ 2 (K and V) × num_layers × num_kv_heads × head_dim × bytes_per_param
```

Multiply by (context length × concurrent requests) and it grows fast — at high
concurrency the KV cache can rival or exceed the weights in memory. This is
exactly why the inference engine's KV management (paging, eviction) matters so
much (see §4).

### Practical starting tiers

| Workload | Model class | Suggested GPU | Notes |
|----------|-------------|---------------|-------|
| High-volume simple tasks (summaries, classification, routing) | 7–8B, quantized | 1× L40S / A10G / A100-40GB | cheapest path; great fit for the `fast` route |
| Mid complexity, RAG answers | 13–34B, quantized | 1× A100-80GB / H100-80GB | room for healthy KV cache + batching |
| Strong reasoning, long context | 70B+ | 2–4× H100-80GB w/ tensor parallelism | only if volume justifies it; else keep on the API |

## 3. Multi-GPU: when one card isn't enough

- **Tensor parallelism (TP)** — split each layer's matrices across GPUs. Needed
  when weights + KV cache don't fit on one card. Wants fast interconnect
  (NVLink).
- **Pipeline parallelism (PP)** — split *layers* across GPUs. Scales across
  nodes but adds latency; usually combined with TP for very large models.

Rule of thumb: reach for TP first (within a node), add PP only when you span
multiple nodes.

## 4. Inference engine choice

Do **not** serve a raw `transformers` model in a loop — throughput will be
terrible. Use a purpose-built engine:

| Engine | Strengths | Pick it when |
|--------|-----------|--------------|
| **vLLM** | PagedAttention KV cache, continuous batching, OpenAI-compatible server, easy | **default choice** — start here |
| **SGLang** | Fast structured output, strong for complex/agentic prompts | structured JSON / heavy prompt reuse |
| **TensorRT-LLM** | Peak throughput/latency on NVIDIA | squeezing max perf, willing to pay setup cost |
| **TGI** | Solid production server from Hugging Face | already in the HF ecosystem |

**Start with vLLM.** Critically, vLLM serves an **OpenAI-compatible** endpoint —
the same shape MiniMax uses — which is what makes the migration in §6 trivial.

### The optimization levers that actually move throughput

- **Continuous batching** — dynamically packs in-flight requests to keep the GPU
  busy; the single biggest throughput win over naive serving.
- **PagedAttention / KV cache management** — stores KV in non-contiguous pages so
  memory isn't wasted on padding; lets you fit far more concurrent requests.
- **Quantization** — FP8/INT8/INT4 to shrink weights and raise throughput.
- **Tensor/pipeline parallelism** — only to fit models that don't fit on one GPU.

## 5. Data residency & compliance (why self-hosting is sometimes *required*)

For a US IT-field-service marketplace, requests can carry client and technician
**PII** and site details. Self-hosting can be a compliance lever, not just a
cost one: the data never leaves your VPC / region. Treat data residency and
retention as a **first-class architectural constraint**, decided before model
choice — not bolted on after. If a class of data legally cannot transit a
third-party API, that workload goes self-hosted regardless of the cost math.

## 6. How the gateway makes the switch cheap

Everything in this repo routes through `LLMProvider` (`app/providers/base.py`).
Because vLLM speaks the same OpenAI-compatible protocol as MiniMax, self-hosting
is essentially:

1. Stand up vLLM on your GPU node, serving e.g. `Qwen2.5-7B-Instruct`.
2. Add a `VLLMProvider` (or just point the existing client at the vLLM base URL —
   the request/response shapes match).
3. Re-route the `fast` logical model to the self-hosted endpoint in
   `MODEL_ROUTES`.

No router, business-logic, caching, queue, or cost-tracking code changes. The
`smart` route can stay on MiniMax. That's the whole payoff of building the
gateway in Part 1: **the expensive architectural decision (self-host vs API)
becomes a config change instead of a rewrite.**

## 7. Recommendation summary

- Ship the MVP on the **MiniMax API** (Part 1). No GPUs, fastest to value.
- Add **caching + queue + autoscaling** (Part 6) to cut cost and absorb spikes.
- Instrument **cost per task** (already built in) so you know your real per-task
  spend.
- Self-host **only** the highest-volume, simplest task(s) — and **only** once the
  measured API bill clears GPU + ops cost, or when **compliance requires** it.
- Run self-hosted on **vLLM**, quantized, with continuous batching, sized by the
  VRAM math above. Keep complex reasoning on the API.
