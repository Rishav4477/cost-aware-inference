"""Runs in CI with real Redis; skipped locally unless TEST_REDIS_URL is set."""

import asyncio
import os
import uuid

import pytest

from inference.models import Tenant
from inference.store import RedisStore


@pytest.mark.skipif(not os.getenv("TEST_REDIS_URL"), reason="Needs Redis service")
async def test_redis_atomic_limits_and_leases():
    store = RedisStore(os.environ["TEST_REDIS_URL"])
    tenant = Tenant(
        id="test-" + uuid.uuid4().hex,
        key_env="TEST",
        daily_budget_usd=0.00001,
        requests_per_minute=5,
    )
    try:
        assert sum(await asyncio.gather(*(store.budget(tenant, 1) for _ in range(50)))) == 10
        assert sum(await asyncio.gather(*(store.reserve(tenant, 1, 0) for _ in range(20)))) == 5
        async with store.lease("test-lock:" + tenant.id) as acquired:
            assert acquired
            async with store.lease("test-lock:" + tenant.id) as second:
                assert not second
    finally:
        await store.close()


@pytest.mark.skipif(not os.getenv("TEST_REDIS_URL"), reason="Needs Redis service")
async def test_two_gateways_coalesce_using_shared_redis(cfg):
    import httpx
    from conftest import response

    from inference.gateway import Gateway
    from inference.models import CompletionRequest
    from inference.observability import Metrics

    cfg.tenants[0].id = "concurrent-" + uuid.uuid4().hex
    calls = []

    async def handler(req):
        calls.append(req)
        await asyncio.sleep(0.03)
        return response()

    stores = [RedisStore(os.environ["TEST_REDIS_URL"]) for _ in range(2)]
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateways = [Gateway(cfg, store, Metrics(), client) for store in stores]
            body = CompletionRequest(messages=[{"role": "user", "content": "same request"}])
            results = await asyncio.gather(
                *(gateways[i % 2].complete(cfg.tenants[0], body) for i in range(20))
            )
            assert len(calls) == 1
            assert sum(r["routing"]["cache_hit"] == "exact" for r in results) == 19
    finally:
        for store in stores:
            await store.close()
