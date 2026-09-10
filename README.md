# Cost-Aware Multi-Cloud AI Inference Platform

A runnable inference gateway that chooses an eligible model endpoint using cost, latency, utilization, and availability. It supports vLLM endpoints hosted in AWS, Azure, GCP, or a trusted private environment. The repository includes a local simulation, shared-state and Kafka integrations, deployment charts, infrastructure modules, tests, and an observability dashboard.

**Status:** initial implementation. Local HTTP demo and automated tests are verified; cloud GPU deployment and real-provider performance are not yet verified. No claimed 35% cloud savings, contribution counts, or production uptime. See [validation evidence](docs/VALIDATION.md).

## Run locally in five minutes

Requires Python 3.12. No cloud account, GPU, Docker, Redis, or Kafka is needed for this mode.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.lock
python scripts/run_demo.py
```

Open <http://127.0.0.1:8000/docs>. The script starts three clearly labeled **mock providers**, plus the gateway. In another terminal with the virtual environment active:

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

Compose runs the gateway, job worker, signal publisher, three mock model services, Redis with AOF, a Kafka-compatible Redpanda broker, Prometheus, and Grafana. Ports bind to localhost. Use Grafana at <http://127.0.0.1:3000> with username `admin` and the password from `.env`; the dashboard provisions automatically. Prometheus is at <http://127.0.0.1:9090>.

`docker compose down` preserves state. `docker compose down -v` intentionally deletes demo Redis/Kafka volumes. Compose is a single-node development stack, not an HA cloud deployment.

## What is implemented

| Capability | Implementation |
| --- | --- |
| Model gateway | Authenticated non-streaming chat completions with request validation and model aliases |
| Multi-cloud routing | Weighted cost/latency/utilization/quality score, hard model/cloud/privacy/cost filters |
| Reliability | Per-provider bounded concurrency, per-attempt timeout, overall deadline, circuit breakers, failover |
| Tenant controls | API keys, atomic request/token limits, daily conservative cost reservations |
| Cache | Tenant- and policy-isolated exact cache; cross-replica deterministic request coalescing |
| Semantic cache | Optional real embedding endpoint, cosine similarity, bounded index, TTL, explicit per-request opt-in |
| Privacy | Sensitive requests only reach configured trusted providers; no caching, embeddings, or async persistence |
| Background inference | Kafka job envelopes, tenant-owned status API, idempotency keys, terminal-result deduplication |
| Live signals | Validated versioned pricing/health/utilization events via Kafka, shared Redis snapshots |
| Model serving | vLLM Helm chart; continuous batching is handled by the inference engine |
| Observability | Prometheus metrics, Grafana dashboard, optional OTLP traces without prompt attributes |
| Deployment | Non-root gateway image, Helm gateway/worker/signal deployments, HPA/PDB, reusable Terraform serving module |
| Quality | Unit/API/concurrency tests, real-Redis CI test, Compose smoke workflow, reproducible load generator |

Native Bedrock, Azure OpenAI, and Vertex proprietary API protocols are not implemented. The real integration is **OpenAI-compatible vLLM services deployed in those clouds**. Streaming, tools, multimodal requests, automatic model-quality evaluation, cloud account provisioning, and automatic GPU-price discovery are outside this initial version.

## Architecture

```mermaid
flowchart TD
    C[Client] --> G[FastAPI gateway]
    G --> R[Redis quotas and cache]
    G --> S[Weighted scheduler]
    S --> A[AWS vLLM]
    S --> Z[Azure vLLM]
    S --> P[GCP vLLM]
    G --> K[Kafka jobs]
    K --> W[Inference workers]
    W --> S
    T[Signal publisher] --> E[Kafka signals]
    E --> U[Signal consumer]
    U --> R
    G --> M[Prometheus and Grafana]
    W --> M
```

Use one Uvicorn process per pod; scale gateway pods through the HPA. Quotas, cache and jobs share Redis. Circuit state and concurrency limits are per process; aggregate provider capacity must account for replica count. Kafka jobs process sequentially per worker; scale workers up to the job-topic partition count. See [architecture and tradeoffs](docs/ARCHITECTURE.md).

## API and configuration

See [API examples](docs/API.md), [deployment guide](docs/DEPLOYMENT.md), and [operations runbook](docs/RUNBOOK.md).

`CONFIG_PATH` selects YAML. `config/demo.yaml` uses host-loopback mocks; `config/compose.yaml` uses Docker DNS. `config/production.example.yaml` is a template requiring real endpoint URLs, secrets and prices. `REDIS_URL` and `KAFKA_BOOTSTRAP_SERVERS` are environment variables. Production refuses to start without Redis or configured tenant keys. Do not deploy `demo: true` with real customer traffic.

Optional semantic reuse requires `embedding_url`, `embedding_model`, and optionally `EMBEDDING_API_KEY`. It is disabled by default. Exact cache is also bypassed for nonzero temperature. See the privacy and approximation limitations in [SECURITY.md](SECURITY.md).

## Tests and evidence

```bash
ruff check .
ruff format --check .
python -m pytest -q
# Real Redis integration test, against a disposable test database:
TEST_REDIS_URL=redis://localhost:6379/15 python -m pytest tests/test_redis_integration.py -q
```

GitHub Actions defines lint/tests, Redis integration, Helm/Terraform validation, and a full Compose/Kafka smoke test. See the repository Actions tab for the status of remote validation jobs. The checked-in [local benchmark JSON](docs/benchmark-local.json) records actual mock-service measurements, not GPU throughput or cloud savings.

## Repository map

- `inference/`: API, routing, state, cache, jobs, workers, telemetry, mock server.
- `tests/`: policy, concurrency, failure, API, cache, and integration tests.
- `scripts/`: demo launcher, smoke test, load generator, signal publisher.
- `deploy/`: gateway and vLLM Helm charts; multi-context Terraform serving deployment.
- `observability/`: provisioned dashboard and Prometheus scrape configuration.
- `docs/`: architecture, API, deployment, operations, validation, and decisions.

Private during development. An open-source license has deliberately not been selected; do so before making the repository public. See [contributing](CONTRIBUTING.md).
