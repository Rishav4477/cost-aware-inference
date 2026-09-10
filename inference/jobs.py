import asyncio
import hashlib
import json

from fastapi import HTTPException

from .kafka_config import kafka_options
from .models import CompletionRequest


class Jobs:
    def __init__(self, settings, store, gateway):
        self.settings, self.store, self.gateway = settings, store, gateway
        self.producer = None
        self.tasks = set()
        self.local_slots = asyncio.Semaphore(8)

    async def start(self):
        if self.settings.kafka_bootstrap:
            from aiokafka import AIOKafkaProducer

            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.settings.kafka_bootstrap,
                **kafka_options(),
                enable_idempotence=True,
                value_serializer=lambda v: json.dumps(v).encode(),
            )
            await self.producer.start()

    async def stop(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if self.producer:
            await self.producer.stop()

    async def submit(self, tenant, request, idempotency_key):
        if request.sensitive:
            raise HTTPException(
                400, "Sensitive requests must use synchronous inference; jobs persist prompts"
            )
        if not self.producer and not self.settings.demo:
            raise HTTPException(503, "Async queue is not configured")
        digest = hashlib.sha256((tenant.id + ":" + idempotency_key).encode()).hexdigest()
        job_id = "job-" + digest
        fingerprint = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        async with self.store.lease("submit:" + job_id, 30) as acquired:
            if not acquired:
                raise HTTPException(409, "Concurrent submission; retry with the same key")
            existing = await self.store.get(job_id)
            if existing and existing["fingerprint"] != fingerprint:
                raise HTTPException(409, "Idempotency key already used with a different request")
            if existing and existing["status"] != "publishing":
                return self.public(existing)
            if not existing:
                # A separate admission guard bounds persistent job payload growth.
                if not await self.store.reserve(tenant, 0, 0):
                    raise HTTPException(429, "Submission quota exceeded")
                existing = {
                    "id": job_id,
                    "tenant": tenant.id,
                    "fingerprint": fingerprint,
                    "status": "publishing",
                    "request": request.model_dump(),
                    "result": None,
                    "error": None,
                }
                await self.store.set(job_id, existing, 86400)
            if self.producer:
                try:
                    await asyncio.wait_for(
                        self.producer.send_and_wait(
                            "inference.jobs", {"id": job_id}, key=job_id.encode()
                        ),
                        10,
                    )
                except Exception:
                    raise HTTPException(
                        503, "Queue unavailable; retry the same Idempotency-Key"
                    ) from None
            if not self.producer:
                if len(self.tasks) >= 256:
                    await self.store.delete(job_id)
                    raise HTTPException(503, "Demo job queue is full")
                existing["status"] = "queued"
                await self.store.set(job_id, existing, 86400)
                task = asyncio.create_task(self.run_local(job_id))
                self.tasks.add(task)
                task.add_done_callback(self.tasks.discard)
            return self.public(await self.store.get(job_id))

    async def run_local(self, job_id):
        async with self.local_slots:
            await self.process(job_id)

    async def process(self, job_id):
        while True:
            async with self.store.lease("job-lock:" + job_id, 130) as acquired:
                if acquired:
                    job = await self.store.get(job_id)
                    if not job or job["status"] in ("completed", "failed"):
                        return
                    tenant = next((t for t in self.settings.tenants if t.id == job["tenant"]), None)
                    if tenant is None:
                        job.update(
                            status="failed", error="Tenant no longer configured", request=None
                        )
                    else:
                        try:
                            result = await self.gateway.complete(
                                tenant, CompletionRequest(**job["request"])
                            )
                            job.update(status="completed", result=result, error=None, request=None)
                        except HTTPException as e:
                            job.update(status="failed", error=e.detail, request=None)
                    await self.store.set(job_id, job, 86400)
                    return
            await asyncio.sleep(0.1)

    async def get(self, tenant, job_id):
        job = await self.store.get(job_id)
        if not job or job["tenant"] != tenant.id:
            raise HTTPException(404, "Job not found")
        return self.public(job)

    @staticmethod
    def public(job):
        result = {k: job[k] for k in ("id", "status", "result", "error")}
        if result["status"] == "publishing":
            result["status"] = "queued"
        return result
