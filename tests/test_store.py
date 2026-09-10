import asyncio

from inference.store import MemoryStore


async def test_atomic_budget_under_concurrency(cfg):
    store = MemoryStore()
    cfg.tenants[0].daily_budget_usd = 0.000010
    results = await asyncio.gather(*(store.budget(cfg.tenants[0], 1) for _ in range(100)))
    assert sum(results) == 10


async def test_atomic_rate_limit(cfg):
    store = MemoryStore()
    cfg.tenants[0].requests_per_minute = 5
    results = await asyncio.gather(*(store.reserve(cfg.tenants[0], 10, 0) for _ in range(30)))
    assert sum(results) == 5


async def test_lease_release_and_expiry():
    store = MemoryStore()
    async with store.lease("a") as first:
        assert first
        async with store.lease("a") as second:
            assert not second
    async with store.lease("a") as third:
        assert third
    await store.set("expired", 1, ttl=-1)
    assert await store.get("expired") is None
