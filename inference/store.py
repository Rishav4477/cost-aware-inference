"""Shared state. Atomic quota reservation prevents concurrent overspend locally.

Budget figures are conservative admission reservations, not cloud billing records.
Redis persistence/HA is an operator responsibility; errors fail requests closed.
"""

import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager


class MemoryStore:
    def __init__(self):
        self.values = {}
        self.mutex = asyncio.Lock()

    async def get(self, key):
        item = self.values.get(key)
        if item is None:
            return None
        if item[0] < time.time():
            self.values.pop(key, None)
            return None
        return item[1]

    async def set(self, key, value, ttl=300):
        self.values[key] = (time.time() + ttl, value)
        if len(self.values) > 10000:
            self.values = {k: v for k, v in self.values.items() if v[0] > time.time()}
            if len(self.values) > 10000:
                raise RuntimeError("Demo store capacity reached")

    async def delete(self, key):
        self.values.pop(key, None)

    async def reserve(self, tenant, tokens, microdollars):
        minute, day = int(time.time() // 60), int(time.time() // 86400)
        keys = [
            f"rpm:{tenant.id}:{minute}",
            f"tpm:{tenant.id}:{minute}",
            f"budget:{tenant.id}:{day}",
        ]
        async with self.mutex:
            vals = [int(await self.get(k) or 0) for k in keys]
            limits = [
                tenant.requests_per_minute,
                tenant.tokens_per_minute,
                int(tenant.daily_budget_usd * 1e6),
            ]
            additions = [1, tokens, microdollars]
            if any(v + a > lim for v, a, lim in zip(vals, additions, limits)):
                return False
            for k, v, a in zip(keys, vals, additions):
                await self.set(k, v + a, 90000)
            return True

    async def budget(self, tenant, microdollars):
        key = f"budget:{tenant.id}:{int(time.time() // 86400)}"
        async with self.mutex:
            current = int(await self.get(key) or 0)
            if current + microdollars > int(tenant.daily_budget_usd * 1e6):
                return False
            await self.set(key, current + microdollars, 90000)
            return True

    @asynccontextmanager
    async def lease(self, key, ttl=130):
        token = str(uuid.uuid4())
        async with self.mutex:
            acquired = await self.get(key) is None
            if acquired:
                await self.set(key, token, ttl)
        try:
            yield acquired
        finally:
            async with self.mutex:
                if acquired and await self.get(key) == token:
                    await self.delete(key)

    async def ping(self):
        return True

    async def close(self):
        pass


RESERVE = """
local a = tonumber(redis.call('GET', KEYS[1]) or '0')
local b = tonumber(redis.call('GET', KEYS[2]) or '0')
local c = tonumber(redis.call('GET', KEYS[3]) or '0')
if a+1>tonumber(ARGV[1]) or b+tonumber(ARGV[4])>tonumber(ARGV[2]) or c+tonumber(ARGV[5])>tonumber(ARGV[3]) then return 0 end
redis.call('INCR', KEYS[1]); redis.call('EXPIRE', KEYS[1], 120)
redis.call('INCRBY', KEYS[2], ARGV[4]); redis.call('EXPIRE', KEYS[2], 120)
redis.call('INCRBY', KEYS[3], ARGV[5]); redis.call('EXPIRE', KEYS[3], 90000)
return 1
"""


class RedisStore:
    def __init__(self, url):
        from redis.asyncio import Redis

        self.redis = Redis.from_url(url, decode_responses=True, socket_timeout=3)

    async def get(self, key):
        value = await self.redis.get(key)
        return json.loads(value) if value is not None else None

    async def set(self, key, value, ttl=300):
        await self.redis.set(key, json.dumps(value), ex=ttl)

    async def delete(self, key):
        await self.redis.delete(key)

    async def reserve(self, tenant, tokens, microdollars):
        # Hash tags keep quota keys in one Redis Cluster slot.
        tag = "{" + tenant.id + "}"
        return bool(
            await self.redis.eval(
                RESERVE,
                3,
                f"rpm:{tag}:{int(time.time() // 60)}",
                f"tpm:{tag}:{int(time.time() // 60)}",
                f"budget:{tag}:{int(time.time() // 86400)}",
                tenant.requests_per_minute,
                tenant.tokens_per_minute,
                int(tenant.daily_budget_usd * 1e6),
                tokens,
                microdollars,
            )
        )

    async def budget(self, tenant, microdollars):
        key = "budget:{" + tenant.id + "}:" + str(int(time.time() // 86400))
        script = "local n=tonumber(redis.call('GET',KEYS[1]) or '0'); if n+tonumber(ARGV[1])>tonumber(ARGV[2]) then return 0 end; redis.call('INCRBY',KEYS[1],ARGV[1]); redis.call('EXPIRE',KEYS[1],90000); return 1"
        return bool(
            await self.redis.eval(script, 1, key, microdollars, int(tenant.daily_budget_usd * 1e6))
        )

    @asynccontextmanager
    async def lease(self, key, ttl=130):
        token = json.dumps(str(uuid.uuid4()))
        acquired = bool(await self.redis.set(key, token, nx=True, ex=ttl))
        try:
            yield acquired
        finally:
            if acquired:
                await self.redis.eval(
                    "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) else return 0 end",
                    1,
                    key,
                    token,
                )

    async def ping(self):
        return await self.redis.ping()

    async def close(self):
        await self.redis.aclose()
