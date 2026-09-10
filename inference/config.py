import math
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .models import Provider, Tenant


@dataclass
class Settings:
    providers: list[Provider]
    tenants: list[Tenant]
    redis_url: str = ""
    kafka_bootstrap: str = ""
    demo: bool = False
    cache_ttl: int = 300
    signal_ttl: int = 60
    require_signals: bool = False
    breaker_threshold: int = 2
    breaker_cooldown: float = 5
    attempt_timeout: float = 2
    weights: dict = field(
        default_factory=lambda: {
            "cost": 0.55,
            "latency": 0.25,
            "utilization": 0.15,
            "quality": 0.05,
        }
    )
    embedding_url: str = ""
    embedding_key_env: str = "EMBEDDING_API_KEY"
    embedding_model: str = ""
    semantic_threshold: float = 0.97

    def __post_init__(self):
        if len({p.id for p in self.providers}) != len(self.providers):
            raise ValueError("Duplicate provider ids")
        if len({t.id for t in self.tenants}) != len(self.tenants):
            raise ValueError("Duplicate tenant ids")
        if set(self.weights) - {"cost", "latency", "utilization", "quality"}:
            raise ValueError("Unknown routing weight")
        if not self.providers or not self.tenants:
            raise ValueError("Providers and tenants are required")
        if (
            any(not math.isfinite(v) or v < 0 for v in self.weights.values())
            or sum(self.weights.values()) <= 0
        ):
            raise ValueError("Routing weights must be nonnegative with positive sum")
        if not self.demo and not self.redis_url:
            raise ValueError("Redis is required outside demo mode")
        if not 0 < self.semantic_threshold <= 1:
            raise ValueError("Semantic threshold must be in (0, 1]")
        if any(
            v <= 0
            for v in (
                self.cache_ttl,
                self.signal_ttl,
                self.breaker_threshold,
                self.breaker_cooldown,
                self.attempt_timeout,
            )
        ):
            raise ValueError("Timeouts, TTLs and circuit threshold must be positive")
        for p in self.providers:
            if not p.base_url.startswith(("http://", "https://")):
                raise ValueError("Provider base_url must be HTTP(S)")

    @classmethod
    def load(cls):
        raw = yaml.safe_load(Path(os.getenv("CONFIG_PATH", "config/demo.yaml")).read_text())
        return cls(
            providers=[Provider(**p) for p in raw.pop("providers")],
            tenants=[Tenant(**t) for t in raw.pop("tenants")],
            redis_url=os.getenv("REDIS_URL", ""),
            kafka_bootstrap=os.getenv("KAFKA_BOOTSTRAP_SERVERS", ""),
            **raw,
        )
