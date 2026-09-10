import asyncio

import httpx
import pytest
from conftest import response
from fastapi import HTTPException

from inference.models import CompletionRequest, Tenant


def request(**kwargs):
    return CompletionRequest(messages=[{"role": "user", "content": "Explain caching"}], **kwargs)


async def test_failover_and_metrics(cfg, make_gateway):
    calls = []

    def handler(req):
        calls.append(req.url.host)
        return httpx.Response(503) if req.url.host == "cheap" else response()

    g = make_gateway(handler)
    result = await g.complete(cfg.tenants[0], request())
    assert result["routing"]["provider"] == "backup"
    assert calls == ["cheap", "backup"]
    assert result["routing"]["estimated_cost_usd"] == 35 / 1e6


async def test_timeout_fails_over(cfg, make_gateway):
    async def handler(req):
        if req.url.host == "cheap":
            await asyncio.sleep(1)
        return response()

    result = await make_gateway(handler).complete(cfg.tenants[0], request())
    assert result["routing"]["provider"] == "backup"


async def test_total_deadline(cfg, make_gateway):
    async def handler(req):
        await asyncio.sleep(1)
        return response()

    with pytest.raises(HTTPException) as e:
        await make_gateway(handler).complete(cfg.tenants[0], request(deadline_ms=100))
    assert e.value.status_code == 504


async def test_exact_cache_and_tenant_isolation(cfg, make_gateway):
    calls = []

    def handler(req):
        calls.append(req)
        return response()

    g = make_gateway(handler)
    a = await g.complete(cfg.tenants[0], request())
    b = await g.complete(cfg.tenants[0], request())
    assert b["routing"]["cache_hit"] == "exact" and b["routing"]["estimated_cost_usd"] == 0
    assert a["id"] != b["id"]
    await g.complete(Tenant(id="tenant-b", key_env="OTHER"), request())
    assert len(calls) == 2


@pytest.mark.parametrize("kwargs", [{"sensitive": True}, {"cache": "off"}, {"temperature": 0.5}])
async def test_uncacheable_requests(cfg, make_gateway, kwargs):
    calls = []

    def handler(req):
        calls.append(req)
        return response()

    g = make_gateway(handler)
    await g.complete(cfg.tenants[0], request(**kwargs))
    await g.complete(cfg.tenants[0], request(**kwargs))
    assert len(calls) == 2


async def test_deduplicates_concurrent_requests(cfg, make_gateway):
    calls = []

    async def handler(req):
        calls.append(req)
        await asyncio.sleep(0.04)
        return response()

    g = make_gateway(handler)
    results = await asyncio.gather(*(g.complete(cfg.tenants[0], request()) for _ in range(20)))
    assert len(calls) == 1
    assert sum(r["routing"]["cache_hit"] == "exact" for r in results) == 19


async def test_budget_prevents_upstream_calls(cfg, make_gateway):
    cfg.tenants[0].daily_budget_usd = 0.000001

    def handler(req):
        pytest.fail("Over-budget request reached provider")

    with pytest.raises(HTTPException) as e:
        await make_gateway(handler).complete(cfg.tenants[0], request())
    assert e.value.status_code == 429


async def test_all_backends_fail(cfg, make_gateway):
    with pytest.raises(HTTPException) as e:
        await make_gateway(lambda req: httpx.Response(503)).complete(cfg.tenants[0], request())
    assert e.value.status_code == 503


async def test_malformed_upstream_response_fails_over(cfg, make_gateway):
    def handler(req):
        return httpx.Response(200, json={"choices": []}) if req.url.host == "cheap" else response()

    result = await make_gateway(handler).complete(cfg.tenants[0], request())
    assert result["routing"]["provider"] == "backup"


async def test_policy_cache_separation(cfg, make_gateway):
    g = make_gateway()
    await g.complete(cfg.tenants[0], request())
    result = await g.complete(cfg.tenants[0], request(allowed_clouds=["gcp"]))
    assert result["routing"]["provider"] == "backup"
    assert result["routing"]["cache_hit"] is None
