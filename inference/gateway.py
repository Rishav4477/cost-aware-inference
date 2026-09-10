import asyncio
import copy
import math
import os
import time
import uuid

import httpx
from fastapi import HTTPException
from opentelemetry import trace

from .cache import ResponseCache
from .routing import Router


class Gateway:
    def __init__(self, settings, store, metrics, client):
        self.settings, self.store, self.metrics, self.client = settings, store, metrics, client
        self.router = Router(settings, store)
        self.cache = ResponseCache(settings, store, client)
        self.semaphores = {p.id: asyncio.Semaphore(p.concurrency) for p in settings.providers}
        self.tracer = trace.get_tracer(__name__)

    async def complete(self, tenant, request):
        started = time.monotonic()
        with self.tracer.start_as_current_span("inference.complete"):
            try:
                async with asyncio.timeout(request.deadline_ms / 1000):
                    result = await self._complete(tenant, request, started)
                self.metrics.requests.labels("success").inc()
                return result
            except TimeoutError:
                self.metrics.requests.labels("deadline").inc()
                raise HTTPException(504, "Request deadline exceeded") from None
            except Exception:
                self.metrics.requests.labels("error").inc()
                raise
            finally:
                self.metrics.duration.observe(time.monotonic() - started)

    async def _complete(self, tenant, request, started):
        # Rate admission applies even to cache hits. Charge token allowance conservatively.
        if not await self.store.reserve(tenant, request.token_reservation(), 0):
            raise HTTPException(
                429, "Request or token quota exceeded", headers={"Retry-After": "60"}
            )
        cached, kind = await self.cache.get(tenant, request)
        if cached:
            return self.cached(cached, kind)
        key = "flight:" + self.cache.key(tenant.id, request)
        # Exact deterministic requests can coalesce across gateway replicas.
        if request.cache != "off" and request.temperature == 0 and not request.sensitive:
            async with self.store.lease(key) as acquired:
                if not acquired:
                    while True:
                        await asyncio.sleep(0.025)
                        cached, kind = await self.cache.get(tenant, request)
                        if cached:
                            return self.cached(cached, kind)
                        # Holder failure allows a retry rather than waiting for entire deadline.
                        if await self.store.get(key) is None:
                            return await self.execute(tenant, request, started)
                cached, kind = await self.cache.get(tenant, request)
                return (
                    self.cached(cached, kind)
                    if cached
                    else await self.execute(tenant, request, started)
                )
        return await self.execute(tenant, request, started)

    def cached(self, value, kind):
        value = copy.deepcopy(value)
        value["id"] = "chatcmpl-" + uuid.uuid4().hex
        value["created"] = int(time.time())
        value["routing"].update(cache_hit=kind, estimated_cost_usd=0)
        self.metrics.cache.labels(kind).inc()
        return value

    async def execute(self, tenant, request, started):
        routing_started = time.monotonic()
        choices = await self.router.candidates(request)
        self.metrics.routing.observe(time.monotonic() - routing_started)
        if not choices:
            raise HTTPException(503, "No eligible provider satisfies routing policy")
        # Reserve worst-case attempt costs before any upstream call. Failed attempts may be billed.
        reserved = math.ceil(sum(c.cost for c in choices) * 1e6)
        if sum(c.cost for c in choices) > request.max_cost_usd:
            choices = choices[:1]
            reserved = math.ceil(choices[0].cost * 1e6)
        if not await self.reserve_budget(tenant, reserved):
            raise HTTPException(429, "Daily budget exhausted")
        tried = []
        for c in choices:
            p = c.provider
            remaining = request.deadline_ms / 1000 - (time.monotonic() - started)
            if remaining <= 0:
                raise HTTPException(504, "Request deadline exceeded")
            tried.append(p.id)
            try:
                before = time.monotonic()
                async with asyncio.timeout(min(remaining, self.settings.attempt_timeout)):
                    async with self.semaphores[p.id]:
                        with self.tracer.start_as_current_span("provider.attempt") as span:
                            span.set_attribute("provider.id", p.id)
                            headers = {}
                            if p.api_key_env:
                                secret = os.environ.get(p.api_key_env)
                                if not secret:
                                    raise ValueError("Missing upstream credential")
                                headers["Authorization"] = "Bearer " + secret
                            res = await self.client.post(
                                p.base_url.rstrip("/") + "/chat/completions",
                                headers=headers,
                                json={
                                    "model": p.model,
                                    "messages": [m.model_dump() for m in request.messages],
                                    "temperature": request.temperature,
                                    "max_tokens": request.max_tokens,
                                    "stream": False,
                                },
                            )
                            res.raise_for_status()
                            data = res.json()
                            content = data["choices"][0]["message"]["content"]
                            if not isinstance(content, str):
                                raise ValueError("Invalid upstream response")
                            usage = data.get("usage", {})
                            for field in ("prompt_tokens", "completion_tokens"):
                                if type(usage.get(field)) is not int or usage[field] < 0:
                                    raise ValueError("Upstream token usage missing/invalid")
                self.router.success(p.id, (time.monotonic() - before) * 1000)
                self.metrics.attempts.labels(p.id, "success").inc()
                # Use price snapshot from candidate admission for stable accounting.
                # Candidate carries separate effective input/output prices below.
                cost = (
                    usage["prompt_tokens"] * c.input_price
                    + usage["completion_tokens"] * c.output_price
                ) / 1e6
                self.metrics.cost.labels(p.id).inc(cost)
                result = {
                    "id": "chatcmpl-" + uuid.uuid4().hex,
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": request.model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": content},
                            "finish_reason": data["choices"][0].get("finish_reason", "stop"),
                        }
                    ],
                    "usage": {
                        **usage,
                        "total_tokens": usage["prompt_tokens"] + usage["completion_tokens"],
                    },
                    "routing": {
                        "provider": p.id,
                        "cloud": p.cloud,
                        "attempts": tried,
                        "cache_hit": None,
                        "estimated_cost_usd": cost,
                        "reserved_cost_usd": reserved / 1e6,
                    },
                }
                await self.cache.put(tenant, request, result)
                return result
            except (httpx.HTTPError, TimeoutError, ValueError, KeyError, IndexError, TypeError):
                self.router.failure(p.id)
                self.metrics.attempts.labels(p.id, "error").inc()
        raise HTTPException(503, "All eligible providers failed")

    async def reserve_budget(self, tenant, microdollars):
        # Separate budget operation avoids double-counting rate/token admission.
        return await self.store.budget(tenant, microdollars)
