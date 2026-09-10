import os

from opentelemetry import trace
from prometheus_client import CollectorRegistry, Counter, Histogram


class Metrics:
    def __init__(self):
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "inference_requests", "Completed gateway requests", ["outcome"], registry=self.registry
        )
        self.attempts = Counter(
            "inference_provider_attempts",
            "Backend attempts",
            ["provider", "outcome"],
            registry=self.registry,
        )
        self.cache = Counter(
            "inference_cache_hits", "Cached responses", ["kind"], registry=self.registry
        )
        self.cost = Counter(
            "inference_estimated_cost_usd",
            "Successful inference cost estimate (not a bill)",
            ["provider"],
            registry=self.registry,
        )
        self.duration = Histogram(
            "inference_request_seconds", "End to end duration", registry=self.registry
        )
        self.routing = Histogram(
            "inference_routing_seconds",
            "Scheduler duration",
            registry=self.registry,
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.35, 1),
        )


def configure_tracing():
    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(
            resource=Resource.create({"service.name": "cost-aware-inference"})
        )
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)
        return provider
    return None
