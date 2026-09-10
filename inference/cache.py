"""Tenant/policy scoped exact and optional embedding-based semantic caching."""

import hashlib
import json
import math
import os
import time


class ResponseCache:
    def __init__(self, settings, store, client):
        self.settings, self.store, self.client = settings, store, client
        self.revision = hashlib.sha256(
            json.dumps(
                {
                    "providers": [p.model_dump() for p in settings.providers],
                    "embedding_model": settings.embedding_model,
                    "embedding_url": settings.embedding_url,
                    "threshold": settings.semantic_threshold,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()

    def key(self, tenant_id, request):
        raw = json.dumps([self.revision, tenant_id, request.model_dump()], sort_keys=True)
        return "cache:" + hashlib.sha256(raw.encode()).hexdigest()

    def scope(self, tenant_id, request):
        policy = request.model_dump(exclude={"messages"})
        return (
            "semantic:"
            + hashlib.sha256(
                json.dumps([self.revision, tenant_id, policy], sort_keys=True).encode()
            ).hexdigest()
        )

    async def vector(self, text):
        key = os.getenv(self.settings.embedding_key_env, "")
        r = await self.client.post(
            self.settings.embedding_url,
            json={"model": self.settings.embedding_model, "input": text},
            headers={"Authorization": f"Bearer {key}"} if key else {},
            timeout=1,
        )
        r.raise_for_status()
        v = r.json()["data"][0]["embedding"]
        if not v or any(not isinstance(x, (float, int)) or not math.isfinite(x) for x in v):
            raise ValueError("Invalid embedding")
        return v

    async def get(self, tenant, request):
        if request.cache == "off" or request.sensitive or request.temperature != 0:
            return None, None
        exact = await self.store.get(self.key(tenant.id, request))
        if exact:
            return exact, "exact"
        if request.cache != "semantic" or not self.settings.embedding_url:
            return None, None
        try:
            vector = await self.vector(request.messages[0].content)
            items = await self.store.get(self.scope(tenant.id, request)) or []
            best, score = None, self.settings.semantic_threshold
            for item in items:
                v = item["vector"]
                if item["expires"] <= time.time() or len(v) != len(vector):
                    continue
                norm = math.sqrt(sum(x * x for x in v) * sum(x * x for x in vector))
                similarity = sum(a * b for a, b in zip(v, vector)) / norm if norm else 0
                if similarity >= score:
                    best, score = item["response"], similarity
            return best, "semantic" if best else None
        except Exception:
            # Embedding service failure must not break inference; Redis exact reads fail closed.
            return None, None

    async def put(self, tenant, request, response):
        if request.cache == "off" or request.sensitive or request.temperature != 0:
            return
        await self.store.set(self.key(tenant.id, request), response, self.settings.cache_ttl)
        if request.cache == "semantic" and self.settings.embedding_url:
            try:
                vector = await self.vector(request.messages[0].content)
                key = self.scope(tenant.id, request)
                async with self.store.lease("lock:" + key, 5) as acquired:
                    if acquired:
                        items = [
                            i
                            for i in (await self.store.get(key) or [])
                            if i["expires"] > time.time()
                        ]
                        items.append(
                            {
                                "vector": vector,
                                "response": response,
                                "expires": time.time() + self.settings.cache_ttl,
                            }
                        )
                        await self.store.set(key, items[-100:], self.settings.cache_ttl)
            except Exception:
                pass
