import asyncio
import hmac
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .config import Settings
from .gateway import Gateway
from .jobs import Jobs
from .models import CompletionRequest
from .observability import Metrics, configure_tracing
from .store import MemoryStore, RedisStore


class BodyLimit:
    def __init__(self, app, max_bytes=100000):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        # Buffer bounded request bodies, including chunked uploads.
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            size += len(body)
            if size > self.max_bytes:
                return await Response("Request too large", status_code=413)(scope, receive, send)
            chunks.append(body)
            if not message.get("more_body", False):
                break
        consumed = False

        async def replay():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        return await self.app(scope, replay, send)


def create_app(settings=None, store=None, client=None):
    @asynccontextmanager
    async def lifespan(app):
        cfg = settings or Settings.load()
        keys = {}
        for tenant in cfg.tenants:
            secret = os.getenv(tenant.key_env)
            if not secret or len(secret) < 16:
                raise RuntimeError(f"Set {tenant.key_env} to a key of at least 16 characters")
            if secret in keys:
                raise RuntimeError("Tenant keys must be unique")
            keys[secret] = tenant
        app.state.keys = keys
        app.state.settings = cfg
        app.state.store = store or (RedisStore(cfg.redis_url) if cfg.redis_url else MemoryStore())
        app.state.client = client or httpx.AsyncClient(
            trust_env=not cfg.demo, timeout=30, limits=httpx.Limits(max_connections=200)
        )
        app.state.metrics = Metrics()
        app.state.gateway = Gateway(cfg, app.state.store, app.state.metrics, app.state.client)
        app.state.jobs = Jobs(cfg, app.state.store, app.state.gateway)
        tracing = configure_tracing()
        await app.state.store.ping()
        await app.state.jobs.start()
        try:
            yield
        finally:
            await app.state.jobs.stop()
            if not client:
                await app.state.client.aclose()
            if not store:
                await app.state.store.close()
            if tracing:
                tracing.shutdown()

    app = FastAPI(title="Cost-Aware Multi-Cloud Inference", version="0.1.0", lifespan=lifespan)
    app.add_middleware(BodyLimit)

    async def authenticate(request: Request, authorization: str = Header(default="")):
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "Bearer API key required")
        supplied = authorization[7:]
        for key, tenant in request.app.state.keys.items():
            if hmac.compare_digest(key.encode(), supplied.encode()):
                return tenant
        raise HTTPException(401, "Invalid API key")

    @app.get("/healthz")
    async def health():
        return {"status": "ok"}

    @app.get("/readyz")
    async def ready(request: Request):
        try:
            await asyncio.wait_for(request.app.state.store.ping(), 2)
        except Exception:
            raise HTTPException(503, "State store unavailable") from None
        return {"status": "ready"}

    @app.get("/metrics", include_in_schema=False)
    async def metrics(request: Request):
        # Deploy on an internal service; restrict /metrics at the ingress.
        return Response(
            generate_latest(request.app.state.metrics.registry), media_type=CONTENT_TYPE_LATEST
        )

    @app.get("/v1/models")
    async def models(request: Request, tenant=Depends(authenticate)):
        aliases = sorted({a for p in request.app.state.settings.providers for a in p.aliases})
        return {
            "object": "list",
            "data": [{"id": a, "object": "model", "owned_by": "platform"} for a in aliases],
        }

    @app.post("/v1/chat/completions")
    async def completion(body: CompletionRequest, request: Request, tenant=Depends(authenticate)):
        return await request.app.state.gateway.complete(tenant, body)

    @app.post("/v1/jobs", status_code=202)
    async def submit(
        body: CompletionRequest,
        request: Request,
        tenant=Depends(authenticate),
        idempotency_key: str = Header(min_length=1, max_length=128),
    ):
        return await request.app.state.jobs.submit(tenant, body, idempotency_key)

    @app.get("/v1/jobs/{job_id}")
    async def job(job_id: str, request: Request, tenant=Depends(authenticate)):
        return await request.app.state.jobs.get(tenant, job_id)

    return app


app = create_app()
