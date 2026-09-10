# Changelog

## 0.2.0 — Public demo UI and hosted sandbox

- Added a responsive browser playground for testing cost-aware routing behavior.
- Added a rate-limited `/public/infer` path that reuses the existing gateway without exposing tenant credentials.
- Added in-process AWS/Azure/GCP provider simulators for safe public demonstrations of routing and failover.
- Added live provider/routing/service status to the UI, including per-request cost, attempts, cache state, and token usage.
- Added `config/public-demo.yaml` and a Render Blueprint with a Redis-compatible Key Value service.
- Updated Docker packaging and README documentation for the public deployment path.

Provider responses, prices, and latency/utilization inputs in the public sandbox are simulations. They are not cloud benchmarks or measured savings.

## 0.1.0 — Initial implementation

- FastAPI gateway with weighted multi-cloud routing, privacy constraints, failover and quotas.
- Exact and optional semantic caching, deterministic request coalescing, Kafka jobs and signals.
- Local three-provider mock demo, HTTP smoke test and reproducible load generator.
- Prometheus/Grafana/OTLP observability, Docker/Helm/Terraform assets and CI workflows.
- Unit/API/concurrency tests and operational documentation.

Deployment artifacts are provided for validation in the owner's cloud environment. Local benchmark results use mocks. No production SLA or cloud cost reduction is claimed.
