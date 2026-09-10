from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Message(StrictModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=32000)


class CompletionRequest(StrictModel):
    model: str = Field(default="small", min_length=1, max_length=100)
    messages: list[Message] = Field(min_length=1, max_length=32)
    max_tokens: int = Field(default=128, ge=1, le=4096)
    temperature: float = Field(default=0, ge=0, le=2)
    sensitive: bool = False
    allowed_clouds: list[Literal["aws", "azure", "gcp", "local"]] = Field(default_factory=list)
    max_cost_usd: float = Field(default=1, gt=0, le=100)
    deadline_ms: int = Field(default=10000, ge=100, le=120000)
    cache: Literal["off", "exact", "semantic"] = "exact"
    stream: Literal[False] = False

    @model_validator(mode="after")
    def size_limit(self):
        if sum(len(m.content.encode()) for m in self.messages) > 64000:
            raise ValueError("Total message payload exceeds 64KB")
        if self.cache == "semantic" and (
            self.temperature != 0 or len(self.messages) != 1 or self.messages[0].role != "user"
        ):
            raise ValueError("Semantic reuse requires one user message and temperature=0")
        return self

    def token_reservation(self):
        # Conservative UTF-8 byte bound, including per-message framing overhead.
        return sum(len(m.content.encode()) + 16 for m in self.messages) + self.max_tokens


class Provider(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    cloud: Literal["aws", "azure", "gcp", "local"]
    base_url: str
    model: str
    aliases: list[str] = Field(min_length=1)
    api_key_env: str | None = None
    trusted: bool = False
    input_usd_per_million: float = Field(ge=0)
    output_usd_per_million: float = Field(ge=0)
    latency_ms: float = Field(default=100, gt=0)
    utilization: float = Field(default=0, ge=0, le=1)
    quality: float = Field(default=1, gt=0, le=1)
    concurrency: int = Field(default=16, ge=1)


class Signal(StrictModel):
    provider_id: str
    timestamp: float = Field(gt=0)
    healthy: bool = True
    latency_ms: float = Field(gt=0)
    utilization: float = Field(ge=0, le=1)
    input_usd_per_million: float = Field(ge=0)
    output_usd_per_million: float = Field(ge=0)


class Tenant(StrictModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    key_env: str
    requests_per_minute: int = Field(default=60, gt=0)
    tokens_per_minute: int = Field(default=100000, gt=0)
    daily_budget_usd: float = Field(default=10, gt=0)
