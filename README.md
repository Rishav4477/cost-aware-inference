# Cost-Aware Multi-Cloud AI Inference Platform

A multi-cloud AI inference gateway that routes each request to an eligible provider using **cost, latency, utilization, quality, availability, privacy policy, and request-level constraints**.

The project includes a public interactive dashboard, OpenAI-compatible API surface, Redis-backed caching and quotas, circuit-breaker failover, Kafka-backed async jobs, Prometheus/Grafana observability, Docker/Helm/Terraform deployment assets, and OpenAI-compatible vLLM serving targets.

> **Live demo:** https://cost-aware-inference.onrender.com
>
> The hosted sandbox uses the real gateway, scheduler, cache, quota, failover, accounting, and telemetry paths. AWS/Azure/GCP model responses and provider price/latency inputs are intentionally simulated so the demo can remain publicly accessible without GPU spend.

---

## What this project demonstrates

- **Cost-aware routing** across AWS, Azure, and GCP-style inference targets.
- **Weighted provider scoring** using cost, latency, utilization, and model quality.
- **Hard policy filters** for cloud allowlists, privacy/trust, budget, health, and request constraints.
- **Automatic failover** with bounded retries and circuit breakers.
- **Redis-backed state** for cache, quotas, request coalescing, leases, and provider signals.
- **Per-request cost accounting** based on configured provider pricing and token usage.
- **Sensitive-request routing** that restricts traffic to explicitly trusted providers.
- **Kafka/Redpanda asynchronous jobs** for background inference workflows.
- **Prometheus metrics and Grafana dashboards** for request, latency, failure, cache, and cost visibility.
- **OpenAI-compatible inference targets**, including vLLM deployments.
- **Deployment tooling** with Docker Compose, Render, Helm, and Terraform.

---

## Live interactive demo

### [Open the public sandbox →](https://cost-aware-inference.onrender.com)

The browser playground lets you:

1. Enter an inference prompt.
2. Choose which clouds are eligible: **AWS, Azure, GCP**.
3. Change the maximum output size.
4. Enable or disable exact caching.
5. Mark a request as **sensitive** to exercise trusted-provider routing.
6. Simulate an AWS, Azure, or GCP outage.
7. Run the request and inspect the routing decision.

For every request, the dashboard shows the selected provider, cloud, attempt path, cache result, estimated cost, reserved cost, token usage, round-trip time, provider health, configured routing weights, and connected runtime services.

### Good demo prompts

Try these in the playground:

```text
Explain why a cost-aware router might choose a slightly slower cloud provider for an AI inference request.
```

```text
Describe the trade-off between minimizing inference latency and minimizing cloud cost.
```

```text
Explain circuit breakers and failover in a distributed inference platform in simple terms.
```

A few useful experiments:

- Run the same prompt twice with **Exact cache** enabled to observe cache behavior.
- Simulate an outage for the provider that would normally win and inspect the new attempt path.
- Enable **Sensitive request** and observe how the trusted-provider policy changes the eligible provider set.
- Disable one or more clouds and see how policy constraints affect the routing decision.

---

## Architecture

```mermaid
flowchart LR
    U[Browser / API Client] --> G[FastAPI Gateway]

    G --> Q[Quota + Policy Admission]
    Q --> C[Redis Cache / Shared State]
    Q --> R[Weighted Router]

    R --> A[AWS Target]
    R --> Z[Azure Target]
    R --> X[GCP Target]

    A --> O[Cost + Metrics + Traces]
    Z --> O
    X --> O

    G --> K[Kafka / Redpanda]
    K --> W[Async Workers]
    W --> R

    S[Pricing / Health / Utilization Signals] --> K
    K --> C

    O --> P[Prometheus]
    P --> D[Grafana]
```

### Request lifecycle

```text
Request
  ↓
FastAPI validation
  ↓
Tenant quota / budget admission
  ↓
Policy filtering
  ├─ model compatibility
  ├─ cloud allowlist
  ├─ trusted-provider requirement
  ├─ provider health
  ├─ deadline
  └─ request cost limit
  ↓
Weighted candidate scoring
  ↓
Best eligible provider
  ↓
Provider attempt
  ├─ success → accounting + cache + response
  └─ failure → circuit breaker + next candidate
```

The router computes a normalized score approximately as:

```text
score =
    cost_weight        × normalized_cost
  + latency_weight     × normalized_latency
  + utilization_weight × normalized_utilization
  + quality_weight     × quality_penalty
```

The default public sandbox weights are:

| Signal | Weight |
| --- | ---: |
| Cost | 55% |
| Latency | 25% |
| Utilization | 15% |
| Quality | 5% |

Lower score wins after hard policy filters are applied.

---

# Run locally

## Option 1 — Run the public dashboard locally

This is the fastest way to explore the project.

### Requirements

- Python **3.12+**
- Git

No AWS, Azure, GCP, GPU, Redis, Kafka, or Docker account is required for this mode.

### 1. Clone the repository

```bash
git clone https://github.com/Rishav4477/cost-aware-inference.git
cd cost-aware-inference
```

### 2. Create a virtual environment

macOS / Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install -r requirements-dev.lock
```

### 4. Start the public sandbox

macOS / Linux:

```bash
export CONFIG_PATH=config/public-demo.yaml
export PUBLIC_DEMO_ENABLED=true
uvicorn inference.app:app --host 0.0.0.0 --port 8000
```

Windows PowerShell:

```powershell
$env:CONFIG_PATH="config/public-demo.yaml"
$env:PUBLIC_DEMO_ENABLED="true"
uvicorn inference.app:app --host 0.0.0.0 --port 8000
```

The sandbox automatically generates ephemeral internal demo credentials when none are supplied.

Now open:

```text
http://127.0.0.1:8000
```

API documentation:

```text
http://127.0.0.1:8000/docs
```

Stop the server with `Ctrl+C`.

---

## Option 2 — Run the original local API demo

This starts three mock providers plus the authenticated gateway.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.lock
python scripts/run_demo.py
```

Then send a request from another terminal:

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H 'Authorization: Bearer local-demo-key-change-me' \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "small",
    "messages": [
      {
        "role": "user",
        "content": "Explain why caching can reduce inference cost"
      }
    ]
  }'
```

Additional checks:

```bash
python scripts/smoke.py
python scripts/benchmark.py --requests 10000 --concurrency 32
```

The benchmark uses local mock providers. It is **not** a GPU throughput or real-cloud cost benchmark.

---

## Option 3 — Run the full local platform with Docker

The full Compose stack includes:

- FastAPI gateway
- inference worker
- provider signal publisher
- three mock provider services
- Redis
- Redpanda / Kafka-compatible broker
- Prometheus
- Grafana

Start everything:

```bash
cp .env.example .env
docker compose up --build -d
```

Run the smoke test:

```bash
python scripts/smoke.py
```

Useful local endpoints:

| Service | Address |
| --- | --- |
| Gateway | `http://127.0.0.1:8000` |
| API docs | `http://127.0.0.1:8000/docs` |
| Grafana | `http://127.0.0.1:3000` |
| Prometheus | `http://127.0.0.1:9090` |

Stop the stack:

```bash
docker compose down
```

Remove local Redis/Kafka volumes as well:

```bash
docker compose down -v
```

---

## Public API example

The hosted browser sandbox exposes a limited public inference endpoint without requiring visitors to receive a tenant API key.

```bash
curl https://cost-aware-inference.onrender.com/public/infer \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "Explain cost-aware AI inference routing",
    "allowed_clouds": ["aws", "azure", "gcp"],
    "fail_clouds": [],
    "cache": "exact",
    "max_tokens": 128,
    "sensitive": false
  }'
```

The public sandbox applies request-size, token, deadline, and per-IP rate limits so it can remain safely accessible.

For the authenticated API and additional examples, see [`docs/API.md`](docs/API.md).

---

## Core capabilities

| Capability | Implementation |
| --- | --- |
| Gateway | FastAPI, request validation, API-key auth, model aliases |
| Routing | Weighted cost / latency / utilization / quality scheduler |
| Policy | Cloud allowlists, privacy trust, health, deadline and budget filters |
| Reliability | Timeouts, bounded concurrency, circuit breakers and provider failover |
| Cache | Tenant-isolated exact cache and request coalescing |
| Semantic cache | Optional embedding-based similarity reuse with TTL and bounded index |
| Quotas | Atomic request/token limits and conservative daily cost reservation |
| Privacy | Sensitive requests restricted to trusted providers and excluded from reuse paths |
| Async jobs | Kafka job envelopes, idempotency, worker processing and result deduplication |
| Live signals | Versioned pricing / health / utilization events with Redis snapshots |
| Observability | Prometheus metrics, Grafana dashboard and optional OTLP traces |
| Serving | OpenAI-compatible vLLM deployment target |
| Infrastructure | Docker Compose, Render, Helm and Terraform |
| Testing | Unit, API, concurrency, Redis integration and Compose smoke coverage |

---

## Configuration profiles

`CONFIG_PATH` selects the runtime YAML configuration.

| File | Purpose |
| --- | --- |
| `config/public-demo.yaml` | Browser sandbox with in-process simulated cloud providers |
| `config/demo.yaml` | Original lightweight local mock demo |
| `config/compose.yaml` | Full Docker Compose environment |
| `config/production.example.yaml` | Template for real OpenAI-compatible provider endpoints |

Important environment variables include:

```text
CONFIG_PATH
REDIS_URL
KAFKA_BOOTSTRAP_SERVERS
PUBLIC_DEMO_ENABLED
```

Production deployments must use real tenant credentials and shared state. Do not use the public-demo configuration for customer traffic.

---

## Real cloud deployment model

The project is designed so each provider can point to an OpenAI-compatible inference service running in a different cloud, for example:

```text
                        FastAPI Gateway
                              │
                 ┌────────────┼────────────┐
                 │            │            │
                 ▼            ▼            ▼
               AWS          Azure         GCP
              vLLM          vLLM          vLLM
                 │            │            │
                 └────────────┼────────────┘
                              │
                     Redis + Kafka +
                  Prometheus / Grafana
```

The repository includes Helm and Terraform assets for this deployment model, but the public Render sandbox intentionally uses simulated providers instead of always-on cloud GPUs.

Native proprietary Bedrock, Azure OpenAI, and Vertex AI protocols are not implemented in this version. Real provider integration currently targets OpenAI-compatible endpoints such as vLLM.

---

## Deploy on Render

A Render Blueprint is included in [`render.yaml`](render.yaml).

It defines:

- the public web service;
- a Redis-compatible Render Key Value store;
- the public-demo configuration;
- generated internal demo credentials;
- the shared `REDIS_URL` connection;
- `/readyz` health checking.

The currently hosted deployment is available at:

### https://cost-aware-inference.onrender.com

---

## Testing

Run the core test suite:

```bash
ruff check .
ruff format --check .
python -m pytest -q
```

With a local Redis instance:

```bash
TEST_REDIS_URL=redis://localhost:6379/15 \
python -m pytest tests/test_redis_integration.py -q
```

GitHub Actions also defines lint/tests, Redis integration, Helm/Terraform validation, and a full Compose/Kafka smoke test.

Validation notes and benchmark evidence are documented in [`docs/VALIDATION.md`](docs/VALIDATION.md).

---

## Repository structure

```text
cost-aware-inference/
├── inference/          # gateway, router, cache, jobs, workers and telemetry
├── web/                # public interactive dashboard
├── config/             # demo, compose and production configuration profiles
├── tests/              # unit, API, concurrency and integration tests
├── scripts/            # demo launcher, smoke tests and load generation
├── deploy/             # Helm charts and Terraform infrastructure
├── observability/      # Prometheus and Grafana configuration
├── docs/               # architecture, API, deployment and operations docs
├── docker-compose.yml
├── render.yaml
└── README.md
```

---

## Design docs

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — architecture and trade-offs
- [`docs/API.md`](docs/API.md) — API usage and examples
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — deployment guide
- [`docs/RUNBOOK.md`](docs/RUNBOOK.md) — operations runbook
- [`docs/VALIDATION.md`](docs/VALIDATION.md) — validation evidence and scope
- [`SECURITY.md`](SECURITY.md) — security considerations
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — contribution workflow

---

## Scope and transparency

The public demo is intended to demonstrate the **control plane** rather than claim production-scale GPU performance.

What is real in the hosted demo:

- gateway request handling;
- routing and policy decisions;
- cache behavior;
- quotas and cost reservation;
- circuit-breaker logic;
- failover;
- Redis-backed state;
- routing metadata and estimated-cost accounting.

What is simulated in the hosted demo:

- model-generated provider responses;
- AWS/Azure/GCP latency inputs;
- utilization values;
- provider pricing snapshots.

No claim is made that the public sandbox represents measured AWS, Azure, or GCP GPU throughput, pricing, savings, or production uptime.

---

## Contributing

Contributions, bug reports, and design discussions are welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a pull request.

If you plan to make a public fork or redistribute the project, check the repository license status first. A license should be selected before broad external reuse or contribution is encouraged.
