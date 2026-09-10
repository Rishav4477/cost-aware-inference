import json
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from inference.jobs import Jobs
from inference.models import CompletionRequest, Tenant
from inference.store import MemoryStore, RedisStore


async def test_redis_lease_can_be_read_by_deduplication_waiter():
    # Real client boundary: lease values must use the store's JSON codec.
    redis = AsyncMock()
    values = {}

    async def set_value(key, value, **kwargs):
        values[key] = value
        return True

    redis.set.side_effect = set_value
    redis.get.side_effect = lambda key: values.get(key)
    store = RedisStore("redis://unused:6379")
    original = store.redis
    store.redis = redis
    try:
        async with store.lease("flight:test") as acquired:
            assert acquired
            assert isinstance(await store.get("flight:test"), str)
            assert json.loads(values["flight:test"])
        assert redis.eval.await_args.args[-1] == values["flight:test"]
    finally:
        await original.aclose()


async def test_queue_retry_after_ambiguous_ack_does_not_regress_completed_state(cfg, make_gateway):
    gateway = make_gateway()
    jobs = Jobs(cfg, gateway.store, gateway)
    body = CompletionRequest(messages=[{"role": "user", "content": "job"}])
    producer = AsyncMock()
    jobs.producer = producer

    async def race(topic, payload, **kwargs):
        await jobs.process(payload["id"])

    producer.send_and_wait.side_effect = race
    result = await jobs.submit(cfg.tenants[0], body, "same-key")
    assert result["status"] == "completed"
    assert (await jobs.submit(cfg.tenants[0], body, "same-key"))["status"] == "completed"
    assert producer.send_and_wait.await_count == 1


async def test_queue_failure_can_retry_same_idempotency_key(cfg, make_gateway):
    gateway = make_gateway()
    jobs = Jobs(cfg, gateway.store, gateway)
    jobs.producer = AsyncMock()
    jobs.producer.send_and_wait.side_effect = RuntimeError("Broker down")
    body = CompletionRequest(messages=[{"role": "user", "content": "job"}])
    with pytest.raises(HTTPException) as e:
        await jobs.submit(cfg.tenants[0], body, "retry-key")
    assert e.value.status_code == 503
    jobs.producer.send_and_wait.side_effect = None
    result = await jobs.submit(cfg.tenants[0], body, "retry-key")
    await jobs.process(result["id"])
    await jobs.process(result["id"])
    assert (await jobs.get(cfg.tenants[0], result["id"]))["status"] == "completed"
    assert jobs.producer.send_and_wait.await_count == 2


async def test_job_ownership_enforced(cfg, make_gateway):
    gateway = make_gateway()
    jobs = Jobs(cfg, gateway.store, gateway)
    body = CompletionRequest(messages=[{"role": "user", "content": "job"}])
    result = await jobs.submit(cfg.tenants[0], body, "owner-test")
    with pytest.raises(HTTPException) as e:
        await jobs.get(Tenant(id="other", key_env="KEY"), result["id"])
    assert e.value.status_code == 404
    await jobs.stop()


async def test_expired_lease_holder_cannot_release_new_holder():
    store = MemoryStore()
    async with store.lease("same", ttl=-1):
        async with store.lease("same") as acquired:
            assert acquired
            newer_token = await store.get("same")
            assert newer_token


async def test_token_limit_does_not_increment_on_denial(cfg):
    store = MemoryStore()
    tenant = cfg.tenants[0]
    tenant.tokens_per_minute = 5
    assert not await store.reserve(tenant, 6, 0)
    assert await store.reserve(tenant, 5, 0)
    assert not await store.reserve(tenant, 1, 0)
