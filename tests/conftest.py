import httpx
import pytest

from inference.config import Settings
from inference.gateway import Gateway
from inference.models import Provider, Tenant
from inference.observability import Metrics
from inference.store import MemoryStore


@pytest.fixture
def cfg(monkeypatch):
    monkeypatch.setenv("TEST_KEY", "test-tenant-key-12345")
    return Settings(
        demo=True,
        breaker_threshold=1,
        attempt_timeout=0.2,
        providers=[
            Provider(
                id="cheap",
                cloud="aws",
                base_url="http://cheap/v1",
                model="test",
                aliases=["small"],
                input_usd_per_million=1,
                output_usd_per_million=2,
                latency_ms=20,
            ),
            Provider(
                id="backup",
                cloud="gcp",
                base_url="http://backup/v1",
                model="test",
                aliases=["small"],
                trusted=True,
                input_usd_per_million=2,
                output_usd_per_million=3,
                latency_ms=40,
            ),
        ],
        tenants=[
            Tenant(
                id="tenant-a",
                key_env="TEST_KEY",
                requests_per_minute=10000,
                tokens_per_minute=10000000,
            )
        ],
    )


def response(content="ok"):
    return httpx.Response(
        200,
        json={
            "choices": [
                {"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
    )


@pytest.fixture
def make_gateway(cfg):
    clients = []

    def factory(handler=None):
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler or (lambda req: response()))
        )
        clients.append(client)
        return Gateway(cfg, MemoryStore(), Metrics(), client)

    return factory
