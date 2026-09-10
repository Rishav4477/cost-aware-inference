"""Kafka consumers: commit offsets only after durable state writes."""

import asyncio
import json
import logging
import time

import httpx
from aiokafka import AIOKafkaConsumer
from prometheus_client import start_http_server

from .config import Settings
from .gateway import Gateway
from .jobs import Jobs
from .kafka_config import kafka_options
from .models import Signal
from .observability import Metrics, configure_tracing
from .store import RedisStore

logger = logging.getLogger(__name__)


async def apply_signal(settings, store, raw):
    signal = Signal(**raw)
    if signal.provider_id not in {p.id for p in settings.providers}:
        raise ValueError("Unknown provider")
    if not 0 <= time.time() - signal.timestamp <= settings.signal_ttl:
        raise ValueError("Signal timestamp is stale or in future")
    key = "signal:" + signal.provider_id
    async with store.lease("signal-lock:" + signal.provider_id, 5) as acquired:
        if not acquired:
            raise RuntimeError("Concurrent signal update; retry delivery")
        previous = await store.get(key)
        if not previous or previous["timestamp"] < signal.timestamp:
            await store.set(key, signal.model_dump(), settings.signal_ttl)


async def consume(settings, store, jobs, signals=False):
    topic = "inference.signals" if signals else "inference.jobs"
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=settings.kafka_bootstrap,
        **kafka_options(),
        group_id="cost-aware-signals" if signals else "cost-aware-jobs",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        max_poll_interval_ms=300000,
        max_poll_records=1,
    )
    await consumer.start()
    try:
        async for message in consumer:
            try:
                raw = json.loads(message.value)
                if signals:
                    await apply_signal(settings, store, raw)
                else:
                    job_id = raw["id"]
                    if not isinstance(job_id, str) or not job_id.startswith("job-"):
                        raise ValueError("Invalid job identifier")
                    await jobs.process(job_id)
            except (ValueError, KeyError, TypeError):
                # Only identifiers/offsets are logged; never prompt payloads.
                logger.warning(
                    "Discarding invalid envelope topic=%s offset=%s", topic, message.offset
                )
            # Infrastructure exceptions exit without commit; restart/rebalance redelivers.
            await consumer.commit()
    finally:
        await consumer.stop()


async def main():
    settings = Settings.load()
    if not settings.redis_url or not settings.kafka_bootstrap:
        raise RuntimeError("Worker requires Redis and Kafka")
    tracing = configure_tracing()
    store = RedisStore(settings.redis_url)
    metrics = Metrics()
    metrics_server, metrics_thread = start_http_server(8001, registry=metrics.registry)
    try:
        async with httpx.AsyncClient(timeout=30, trust_env=not settings.demo) as client:
            jobs = Jobs(settings, store, Gateway(settings, store, metrics, client))
            async with asyncio.TaskGroup() as group:
                group.create_task(consume(settings, store, jobs))
                group.create_task(consume(settings, store, jobs, signals=True))
    finally:
        metrics_server.shutdown()
        metrics_server.server_close()
        metrics_thread.join(timeout=2)
        await store.close()
        if tracing:
            tracing.shutdown()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
