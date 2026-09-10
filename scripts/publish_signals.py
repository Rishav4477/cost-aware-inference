"""Publish health + configured prices periodically. Prices are operator inputs.

For production replace configured price/utilization with your billing/metrics feed.
"""

import asyncio
import json
import os
import time

import httpx
from aiokafka import AIOKafkaProducer

from inference.config import Settings
from inference.kafka_config import kafka_options


async def main():
    cfg = Settings.load()
    producer = AIOKafkaProducer(
        bootstrap_servers=cfg.kafka_bootstrap,
        **kafka_options(),
        enable_idempotence=True,
        value_serializer=lambda v: json.dumps(v).encode(),
    )
    await producer.start()
    try:
        async with httpx.AsyncClient(timeout=2, trust_env=not cfg.demo) as client:
            while True:
                for p in cfg.providers:
                    start = time.monotonic()
                    headers = (
                        {"Authorization": "Bearer " + os.getenv(p.api_key_env, "")}
                        if p.api_key_env
                        else {}
                    )
                    try:
                        # OpenAI-compatible /models validates application readiness.
                        response = await client.get(
                            p.base_url.rstrip("/") + "/models", headers=headers
                        )
                        healthy = response.is_success
                    except httpx.HTTPError:
                        healthy = False
                    payload = {
                        "provider_id": p.id,
                        "timestamp": time.time(),
                        "healthy": healthy,
                        "latency_ms": max(1, (time.monotonic() - start) * 1000),
                        "utilization": p.utilization,
                        "input_usd_per_million": p.input_usd_per_million,
                        "output_usd_per_million": p.output_usd_per_million,
                    }
                    await producer.send_and_wait("inference.signals", payload, key=p.id.encode())
                await asyncio.sleep(5)
    finally:
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
