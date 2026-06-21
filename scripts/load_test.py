"""
Tiny concurrent load test — fires N requests at the API and reports latency
percentiles + cache-hit behaviour. Not a replacement for k6/Locust, but enough
to demonstrate the cache and async paths under concurrency.

Usage:
    python scripts/load_test.py --url http://localhost:8000 --n 50 --concurrency 10
"""

import argparse
import asyncio
import statistics
import time

import httpx


async def one_request(client: httpx.AsyncClient, base: str, i: int) -> tuple[int, float, bool]:
    # Half the requests are identical (to exercise the cache), half unique.
    content = "Reply OK" if i % 2 == 0 else f"Reply OK number {i}"
    start = time.perf_counter()
    resp = await client.post(
        f"{base}/v1/chat",
        json={"messages": [{"role": "user", "content": content}],
              "model": "fast", "max_tokens": 16},
    )
    elapsed = (time.perf_counter() - start) * 1000
    cached = False
    try:
        cached = resp.json().get("cached", False)
    except Exception:
        pass
    return resp.status_code, elapsed, cached


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--concurrency", type=int, default=10)
    args = ap.parse_args()

    sem = asyncio.Semaphore(args.concurrency)
    latencies: list[float] = []
    statuses: list[int] = []
    cache_hits = 0

    async with httpx.AsyncClient(timeout=120) as client:
        async def guarded(i: int):
            nonlocal cache_hits
            async with sem:
                code, ms, cached = await one_request(client, args.url, i)
                statuses.append(code)
                latencies.append(ms)
                if cached:
                    cache_hits += 1

        started = time.perf_counter()
        await asyncio.gather(*(guarded(i) for i in range(args.n)))
        wall = time.perf_counter() - started

    latencies.sort()
    ok = sum(1 for s in statuses if s == 200)
    print(f"requests:    {args.n}  (concurrency {args.concurrency})")
    print(f"success:     {ok}/{args.n}")
    print(f"cache hits:  {cache_hits}")
    print(f"throughput:  {args.n / wall:.1f} req/s")
    print(f"latency ms:  p50={statistics.median(latencies):.0f}  "
          f"p95={latencies[int(len(latencies) * 0.95) - 1]:.0f}  "
          f"max={latencies[-1]:.0f}")


if __name__ == "__main__":
    asyncio.run(main())
