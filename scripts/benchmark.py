"""HTTP load test. Saves observed results, never extrapolated cloud claims."""

import argparse
import asyncio
import collections
import json
import os
import statistics
import time
from pathlib import Path

import httpx


def percentile(values, p):
    return sorted(values)[min(len(values) - 1, int((len(values) - 1) * p))] if values else None


async def run(args):
    latencies = []
    providers = collections.Counter()
    errors = collections.Counter()
    costs = []
    sem = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient(
        trust_env=False,
        timeout=30,
        headers={
            "Authorization": "Bearer " + os.getenv("DEMO_API_KEY", "local-demo-key-change-me")
        },
        limits=httpx.Limits(max_connections=args.concurrency),
    ) as client:
        started = time.monotonic()

        async def one(i):
            async with sem:
                start = time.monotonic()
                try:
                    r = await client.post(
                        args.url + "/v1/chat/completions",
                        json={
                            "messages": [{"role": "user", "content": f"Benchmark request {i}"}],
                            "cache": "off",
                        },
                    )
                    latencies.append((time.monotonic() - start) * 1000)
                    if r.is_success:
                        data = r.json()["routing"]
                        providers[data["provider"]] += 1
                        costs.append(data["estimated_cost_usd"])
                    else:
                        errors[str(r.status_code)] += 1
                except httpx.HTTPError:
                    latencies.append((time.monotonic() - start) * 1000)
                    errors["transport"] += 1

        # Bounded task batches avoid one asyncio task per request for huge runs.
        for start in range(0, args.requests, 1000):
            await asyncio.gather(*(one(i) for i in range(start, min(start + 1000, args.requests))))
        elapsed = time.monotonic() - started
    result = {
        "scenario": args.scenario,
        "requests": args.requests,
        "concurrency": args.concurrency,
        "successes": sum(providers.values()),
        "errors": dict(errors),
        "providers": dict(providers),
        "completion_ratio": sum(providers.values()) / args.requests,
        "elapsed_seconds": elapsed,
        "requests_per_second": args.requests / elapsed,
        "p50_ms": percentile(latencies, 0.5),
        "p95_ms": percentile(latencies, 0.95),
        "p99_ms": percentile(latencies, 0.99),
        "mean_ms": statistics.mean(latencies),
        "estimated_success_cost_usd": sum(costs),
        "note": "End-to-end HTTP latency; prices are configured inputs. Local demo uses no actual LLM or cloud.",
    }
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=10000)
    parser.add_argument("--concurrency", type=int, default=32)
    parser.add_argument("--scenario", default="local-mock")
    parser.add_argument("--output", default="benchmark-local.json")
    args = parser.parse_args()
    if args.requests <= 0 or args.concurrency <= 0:
        parser.error("requests and concurrency must be positive")
    asyncio.run(run(args))
