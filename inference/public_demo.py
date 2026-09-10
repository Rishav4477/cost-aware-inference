import asyncio
import hmac
import os
import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .models import CompletionRequest, Message


CLOUD_DELAYS_MS = {"aws": 55, "azure": 85, "gcp": 120}
CLOUD_LABELS = {"aws": "AWS", "azure": "Azure", "gcp": "GCP"}
_requests_by_ip: dict[str, deque[float]] = defaultdict(deque)


class PublicCompletion(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    max_tokens: int = Field(default=128, ge=1, le=512)
    allowed_clouds: list[str] = Field(default_factory=list)
    fail_clouds: list[str] = Field(default_factory=list)
    cache: str = Field(default="exact", pattern="^(off|exact)$")
    sensitive: bool = False


def _enabled(request: Request):
    if not getattr(request.app.state, "public_demo_enabled", False):
        raise HTTPException(404, "Public demo is disabled")


def _rate_limit(request: Request):
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")
    now = time.monotonic()
    bucket = _requests_by_ip[ip]
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= 30:
        raise HTTPException(429, "Public demo limit reached; retry in a minute")
    bucket.append(now)


def _clouds(values: list[str]):
    valid = {"aws", "azure", "gcp"}
    if any(value not in valid for value in values):
        raise HTTPException(400, "Cloud must be one of: aws, azure, gcp")
    return values


def _provider_auth(request: Request):
    expected = os.getenv("PUBLIC_DEMO_PROVIDER_KEY", "")
    supplied = request.headers.get("authorization", "")
    if not expected or not supplied.startswith("Bearer "):
        raise HTTPException(404, "Not found")
    if not hmac.compare_digest(expected.encode(), supplied[7:].encode()):
        raise HTTPException(404, "Not found")


def create_public_router():
    router = APIRouter(prefix="/public", tags=["public-demo"])

    @router.get("/status")
    async def status(request: Request):
        _enabled(request)
        settings = request.app.state.settings
        providers = []
        for provider in settings.providers:
            if provider.cloud not in CLOUD_LABELS:
                continue
            providers.append(
                {
                    "id": provider.id,
                    "cloud": provider.cloud,
                    "label": CLOUD_LABELS[provider.cloud],
                    "latency_ms": provider.latency_ms,
                    "utilization": provider.utilization,
                    "input_usd_per_million": provider.input_usd_per_million,
                    "output_usd_per_million": provider.output_usd_per_million,
                    "trusted": provider.trusted,
                    "healthy": request.app.state.gateway.router.circuits[provider.id].open_until
                    <= time.monotonic(),
                }
            )
        return {
            "mode": "simulation",
            "notice": "Provider responses and prices are simulated; routing, policy, failover, cache, quotas and accounting use the real gateway code path.",
            "providers": providers,
            "weights": settings.weights,
            "services": {
                "fastapi_gateway": True,
                "router": True,
                "redis": bool(settings.redis_url),
                "kafka": bool(settings.kafka_bootstrap),
                "prometheus": True,
            },
        }

    @router.post("/infer")
    async def infer(body: PublicCompletion, request: Request):
        _enabled(request)
        _rate_limit(request)
        allowed = _clouds(body.allowed_clouds)
        failures = _clouds(body.fail_clouds)
        settings = request.app.state.settings
        tenant_id = os.getenv("PUBLIC_DEMO_TENANT_ID", "public-demo")
        tenant = next((item for item in settings.tenants if item.id == tenant_id), None)
        if tenant is None:
            raise HTTPException(503, "Public demo tenant is not configured")
        messages = []
        if failures:
            messages.append(
                Message(role="system", content="<demo-fail:" + ",".join(sorted(set(failures))) + ">")
            )
        messages.append(Message(role="user", content=body.prompt))
        completion = CompletionRequest(
            model="small",
            messages=messages,
            max_tokens=body.max_tokens,
            temperature=0,
            sensitive=body.sensitive,
            allowed_clouds=allowed,
            max_cost_usd=0.10,
            deadline_ms=5000,
            cache=body.cache,
        )
        result = await request.app.state.gateway.complete(tenant, completion)
        result["demo"] = {
            "mode": "simulation",
            "failed_clouds_requested": failures,
            "provider_response_is_simulated": True,
        }
        return result

    @router.post("/providers/{cloud}/v1/chat/completions", include_in_schema=False)
    async def provider(cloud: str, request: Request):
        _enabled(request)
        _provider_auth(request)
        if cloud not in CLOUD_DELAYS_MS:
            raise HTTPException(404, "Unknown demo provider")
        body = await request.json()
        messages = body.get("messages") or []
        marker = "<demo-fail:"
        failures = set()
        for message in messages:
            content = str(message.get("content", ""))
            if content.startswith(marker) and content.endswith(">"):
                failures.update(content[len(marker) : -1].split(","))
        await asyncio.sleep(CLOUD_DELAYS_MS[cloud] / 1000)
        if cloud in failures:
            raise HTTPException(503, f"Simulated {CLOUD_LABELS[cloud]} outage")
        prompt = next(
            (str(message.get("content", "")) for message in reversed(messages) if message.get("role") == "user"),
            "",
        )
        content = (
            f"[SIMULATED {CLOUD_LABELS[cloud]} PROVIDER] The gateway routed this request successfully. "
            f"Your prompt was: {prompt[:280]}"
        )
        prompt_tokens = max(1, sum(len(str(m.get("content", "")).encode()) for m in messages) // 4)
        completion_tokens = min(int(body.get("max_tokens", 128)), max(1, len(content.encode()) // 4))
        return {
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

    return router
