import time
from dataclasses import dataclass

from .models import Signal


@dataclass
class Circuit:
    failures: int = 0
    open_until: float = 0
    latency_ms: float = 0


@dataclass
class Candidate:
    provider: object
    cost: float
    latency: float
    utilization: float
    input_price: float = 0
    output_price: float = 0
    score: float = 0


class Router:
    def __init__(self, settings, store):
        self.settings, self.store = settings, store
        self.circuits = {p.id: Circuit() for p in settings.providers}

    async def candidates(self, request):
        candidates = []
        now = time.time()
        for p in self.settings.providers:
            circuit = self.circuits[p.id]
            if request.model not in p.aliases or circuit.open_until > time.monotonic():
                continue
            if request.sensitive and not p.trusted:
                continue
            if request.allowed_clouds and p.cloud not in request.allowed_clouds:
                continue
            raw = await self.store.get(f"signal:{p.id}")
            signal = Signal(**raw) if raw else None
            fresh = signal and 0 <= now - signal.timestamp <= self.settings.signal_ttl
            if self.settings.require_signals and not fresh:
                continue
            if fresh and not signal.healthy:
                continue
            inp = signal.input_usd_per_million if fresh else p.input_usd_per_million
            out = signal.output_usd_per_million if fresh else p.output_usd_per_million
            # Conservative admission estimate; actual cost uses returned token usage.
            cost = (
                (request.token_reservation() - request.max_tokens) * inp + request.max_tokens * out
            ) / 1e6
            latency = signal.latency_ms if fresh else (circuit.latency_ms or p.latency_ms)
            utilization = signal.utilization if fresh else p.utilization
            if cost <= request.max_cost_usd and latency <= request.deadline_ms and utilization < 1:
                candidates.append(Candidate(p, cost, latency, utilization, inp, out))
        if not candidates:
            return []
        max_cost = max(c.cost for c in candidates) or 1
        max_latency = max(c.latency for c in candidates) or 1
        w = self.settings.weights
        for c in candidates:
            c.score = (
                w.get("cost", 0) * c.cost / max_cost
                + w.get("latency", 0) * c.latency / max_latency
                + w.get("utilization", 0) * c.utilization
                + w.get("quality", 0) * (1 - c.provider.quality)
            )
        return sorted(candidates, key=lambda c: (c.score, c.provider.id))

    def failure(self, provider_id):
        c = self.circuits[provider_id]
        c.failures += 1
        if c.failures >= self.settings.breaker_threshold:
            c.open_until = time.monotonic() + self.settings.breaker_cooldown

    def success(self, provider_id, latency):
        c = self.circuits[provider_id]
        c.failures, c.open_until = 0, 0
        c.latency_ms = latency if not c.latency_ms else 0.2 * latency + 0.8 * c.latency_ms
