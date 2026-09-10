import time

import httpx
import pytest
from conftest import response

from inference.models import CompletionRequest
from inference.store import MemoryStore
from inference.worker import apply_signal


async def test_semantic_hit_and_privacy(cfg, make_gateway):
    cfg.embedding_url = "http://embedding/v1/embeddings"
    calls = []

    def handler(req):
        calls.append(req.url.host)
        if req.url.host == "embedding":
            return httpx.Response(200, json={"data": [{"embedding": [1, 0, 0]}]})
        return response("cached semantic answer")

    g = make_gateway(handler)

    def body(content, **kw):
        return CompletionRequest(
            messages=[{"role": "user", "content": content}], cache="semantic", **kw
        )

    await g.complete(cfg.tenants[0], body("What is caching?"))
    result = await g.complete(cfg.tenants[0], body("Explain a cache"))
    assert result["routing"]["cache_hit"] == "semantic"
    assert calls.count("cheap") == 1
    embedding_calls = calls.count("embedding")
    await g.complete(cfg.tenants[0], body("Private question", sensitive=True))
    assert calls.count("embedding") == embedding_calls


async def test_signal_ordering(cfg):
    store = MemoryStore()
    signal = {
        "provider_id": "cheap",
        "timestamp": time.time(),
        "healthy": True,
        "latency_ms": 10,
        "utilization": 0,
        "input_usd_per_million": 1,
        "output_usd_per_million": 2,
    }
    await apply_signal(cfg, store, signal)
    await apply_signal(
        cfg, store, {**signal, "timestamp": signal["timestamp"] - 1, "healthy": False}
    )
    assert (await store.get("signal:cheap"))["healthy"]
    for change in (
        {"timestamp": time.time() + 100},
        {"provider_id": "unknown"},
        {"utilization": float("nan")},
    ):
        with pytest.raises(ValueError):
            await apply_signal(cfg, store, {**signal, **change})
