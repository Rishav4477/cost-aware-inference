import time

import pytest

from inference.models import CompletionRequest, Signal
from inference.routing import Router
from inference.store import MemoryStore


@pytest.fixture
def req():
    return CompletionRequest(messages=[{"role": "user", "content": "Explain caches"}])


async def test_cheapest_healthy_provider(cfg, req):
    router = Router(cfg, MemoryStore())
    assert [c.provider.id for c in await router.candidates(req)] == ["cheap", "backup"]


async def test_sensitive_uses_trusted_only(cfg, req):
    req.sensitive = True
    assert [c.provider.id for c in await Router(cfg, MemoryStore()).candidates(req)] == ["backup"]


@pytest.mark.parametrize(
    "changes",
    [
        {"model": "unknown"},
        {"allowed_clouds": ["azure"]},
        {"max_cost_usd": 1e-10},
        {"sensitive": True, "allowed_clouds": ["aws"]},
    ],
)
async def test_hard_constraints_never_relaxed(cfg, req, changes):
    for k, v in changes.items():
        setattr(req, k, v)
    assert await Router(cfg, MemoryStore()).candidates(req) == []


async def test_open_circuit_then_recovery(cfg, req):
    r = Router(cfg, MemoryStore())
    r.failure("cheap")
    assert [c.provider.id for c in await r.candidates(req)] == ["backup"]
    r.circuits["cheap"].open_until = time.monotonic() - 1
    assert (await r.candidates(req))[0].provider.id == "cheap"
    r.success("cheap", 15)
    assert r.circuits["cheap"].failures == 0


async def test_live_signals_and_staleness(cfg, req):
    cfg.require_signals = True
    store = MemoryStore()
    router = Router(cfg, store)
    assert await router.candidates(req) == []
    signal = Signal(
        provider_id="cheap",
        timestamp=time.time(),
        latency_ms=30,
        utilization=0.1,
        input_usd_per_million=4,
        output_usd_per_million=7,
    )
    await store.set("signal:cheap", signal.model_dump())
    choices = await router.candidates(req)
    assert len(choices) == 1 and choices[0].input_price == 4
    signal.healthy = False
    await store.set("signal:cheap", signal.model_dump())
    assert await router.candidates(req) == []
    signal.healthy = True
    signal.timestamp = time.time() - 1000
    await store.set("signal:cheap", signal.model_dump())
    assert await router.candidates(req) == []
