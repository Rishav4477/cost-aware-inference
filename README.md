# Cost-Aware Multi-Cloud AI Inference Platform

A runnable inference gateway that selects an eligible model endpoint using cost, latency, utilization, quality, availability, privacy policy, and per-request constraints. The platform supports OpenAI-compatible vLLM endpoints hosted in AWS, Azure, GCP, or a trusted private environment, and now includes a browser-based public sandbox for demonstrating routing behavior.

**Status:** core gateway implementation is validated locally. The public sandbox uses the real gateway/router/cache/quota/failover code path with intentionally simulated provider responses and illustrative prices. Real cloud GPU deployment and real-provider savings remain unverified; the project does not claim production uptime or measured cloud savings. See [validation evidence](docs/VALIDATION.md).

## Public web demo

The repository includes a responsive dashboard under `web/` and a rate-limited public API under `/public/*`. The dashboard lets visitors:

- send inference requests through the existing `Gateway.complete()` path;
- choose which of AWS, Azure, and GCP are eligible for a request;
- simulate a cloud outage and observe circuit-breaker failover;
- inspect selected cloud/provider, attempt order, cache behavior, token usage, and estimated cost;
- view provider inputs, routing weights, and connected platform services.

The hosted sandbox is deliberately safe to leave public: the browser never receives a tenant API key, prompts are capped at 4,000 characters, requests are limited per IP, and provider responses are deterministic simulations rather than billable model calls. The internal simulator endpoints require a separate server-side bearer secret and are not directly usable by the browser.

The public sandbox is **not** presented as a real three-cloud benchmark. Provider prices, latency inputs, utilization, and responses in `config/public-demo.yaml` are simulation inputs. The scheduler, policy filters, circuit breaker, Redis-backed state, cache, quotas, request accounting, and response routing metadata are the same implementation used by the normal API.

### Run the web sandbox locally

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.lock
export CONFIG_PATH=config/public-demo.yaml
export PUBLIC_DEMO_ENABLED=true
export PUBLIC_DEMO_TENANT_KEY=local-public-demo-key-change-me
export PUBLIC_DEMO_PROVIDER_KEY=local-provider-key-change-me
uvicorn inference.app:app --host 0.0.0.0 --port 8000
```

Open <http://127.0.0.1:8000>. API documentation remains available at <http://127.0.0.1:8000/docs>.

### Deploy the public sandbox on Render

`render.yaml` defines a Docker web service and a private Redis-compatible Render Key Value service. The Blueprint wires `REDIS_URL`, enables the sandbox, generates the internal tenant and simulator-provider secrets, and uses `/readyz` as the health check.

The public deployment intentionally does not run Kafka because the interactive site exercises synchronous routing. Kafka-backed asynchronous jobs remain available in the full Compose/Kubernetes deployments.

## Run the original local API demo

Requires Python 3.12. No cloud account, GPU, Docker, Redis, or Kafka is needed for this mode.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.lock
python scripts/run_demo.py
```

Open <http://127.0.0.1:8000/docs>. The script starts three clearly labeled mock providers plus the gateway. In another terminal:

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H 'Authorization: Bearer local-demo-key-change-me' \
  -H 'Content-Type: application/json' \
  -d '{"model":"small","messages":[{"role":"user","content":"Explain caching"}]}'

python scripts/smoke.py
python scripts/benchmark.py --requests 10000 --concurrency 32
```

Stop with Ctrl-C. Demo data is in memory and disappears on shutdown. The hardcoded demo credential is local-only; set `DEMO_API_KEY` to override it.

## Run the full local stack

```bash
cp .env.example .env
docker compose up --build -d
python scripts/smoke.py
docker compose down
```

Compose runs the gateway, job worker, signal publisher, three mock model services, Redis with AOF, a Kafka-compatible Redpanda broker, Prometheus, and Grafana. Ports bind to localhost. Grafana is at <http://127.0.0.1:3000>; Prometheus is at <http://127.0.0.1:9090>.

`docker compose down` preserves state. `docker compose down -v` intentionally deletes demo Redis/Kafka volumes. Compose is a single-node development stack, not an HA cloud deployment.

## What is implemented

| Capability | Implementation |
| --- | --- |
| Public demo UI | Responsive browser playground, provider state, routing metadata, outage simulation, service topology |
| Public sandbox API | Rate-limited `/public/infer` endpoint with no browser-exposed tenant secret |
| Model gateway | Authenticated non-streaming chat completions with request validation and model aliases |
| Multi-cloud routing | Weighted cost/latency/utilization/quality score, hard model/cloud/privacy/cost filters |
| Reliability | Per-provider bounded concurrency, per-attempt timeout, overall deadline, circuit breakers, failover |
| Tenant controls | API keys, atomic request/token limits, daily conservative cost reservations |
| Cache | Tenant- and policy-isolated exact cache; cross-replica deterministic request coalescing |
| Semantic cache | Optional embedding endpoint, cosine similarity, bounded index, TTL, explicit opt-in |
| Privacy | Sensitive requests only reach configured trusted providers; no caching, embeddings, or async persistence |
| Background inference | Kafka job envelopes, tenant-owned status API, idempotency keys, terminal-result deduplication |
| Live signals | Validated versioned pricing/health/utilization events via Kafka, shared Redis snapshots |
| Model serving | vLLM Helm chart; continuous batching handled by the inference engine |
| Observability | Prometheus metrics, Grafana dashboard, optional OTLP traces without prompt attributes |
| Deployment | Docker, Render Blueprint, Helm gateway/worker/signal deployments, HPA/PDB, Terraform serving module |
| Quality | Unit/API/concurrency tests, real-Redis CI test, Compose smoke workflow, reproducible load generator |

Native Bedrock, Azure OpenAI, and Vertex proprietary API protocols are not implemented. Real model integrations are OpenAI-compatible vLLM services deployed in those clouds. Streaming, tools, multimodal requests, automatic model-quality evaluation, cloud account provisioning, and automatic GPU-price discovery remain outside this version.

## Architecture

```mermaid
flowchart TD
    B[Browser demo] --> P[Public sandbox API]
    C[API client] --> G[FastAPI gateway]
    P --> G
    G --> R[Redis quotas and cache]
    G --> S[Weighted scheduler]
    S --> A[AWS vLLM / demo provider]
    S --> Z[Azure vLLM / demo provider]
    S --> X[GCP vLLM / demo provider]
    G --> K[Kafka jobs]
    K --> W[Inference workers]
    W --> S
    T[Signal publisher] --> E[Kafka signals]
    E --> U[Signal consumer]
    U --> R
    G --> M[Prometheus and Grafana]
    W --> M
```

Use one Uvicorn process per pod and scale gateway pods through the HPA. Quotas, cache, and jobs share Redis. Circuit state and concurrency limits are per process; aggregate provider capacity must account for replica count. Kafka jobs process sequentially per worker; scale workers up to the job-topic partition count. See [architecture and tradeoffs](docs/ARCHITECTURE.md).

## API and configuration

See [API examples](docs/API.md), [deployment guide](docs/DEPLOYMENT.md), and [operations runbook](docs/RUNBOOK.md).

`CONFIG_PATH` selects YAML:

- `config/demo.yaml` — original local three-process simulation;
- `config/public-demo.yaml` — browser sandbox with in-process simulated providers;
- `config/compose.yaml` — full Docker Compose stack;
- `config/production.example.yaml` — template for real OpenAI-compatible inference endpoints.

`REDIS_URL` and `KAFKA_BOOTSTRAP_SERVERS` are environment variables. Production refuses to start without Redis or configured tenant keys. Do not deploy a demo configuration for real customer traffic.

Optional semantic reuse requires `embedding_url`, `embedding_model`, and optionally `EMBEDDING_API_KEY`. It is disabled by default. Exact cache is bypassed for nonzero temperature. See [SECURITY.md](SECURITY.md).

## Tests and evidence

```bash
ruff check .
ruff format --check .
python -m pytest -q
TEST_REDIS_URL=redis://localhost:6379/15 python -m pytest tests/test_redis_integration.py -q
```

GitHub Actions defines lint/tests, Redis integration, Helm/Terraform validation, and a full Compose/Kafka smoke test. The checked-in [local benchmark JSON](docs/benchmark-local.json) records mock-service measurements, not GPU throughput or cloud savings.

## Repository map

- `inference/`: API, routing, state, cache, jobs, workers, telemetry, and public sandbox endpoints.
- `web/`: public demo dashboard served by FastAPI.
- `tests/`: policy, concurrency, failure, API, cache, and integration tests.
- `scripts/`: demo launcher, smoke test, load generator, signal publisher.
- `deploy/`: gateway and vLLM Helm charts; multi-context Terraform serving deployment.
- `observability/`: provisioned dashboard and Prometheus scrape configuration.
- `docs/`: architecture, API, deployment, operations, validation, and decisions.
- `render.yaml`: reproducible public sandbox deployment.

Private during development. An open-source license has deliberately not been selected; choose one before making the repository public. See [CONTRIBUTING.md](CONTRIBUTING.md).
