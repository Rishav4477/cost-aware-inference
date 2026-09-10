# Cost-Aware Multi-Cloud AI Inference Platform

A multi-cloud AI inference gateway that routes each request to an eligible provider using **cost, latency, utilization, quality, availability, privacy policy, and request-level constraints**.

> **Live demo:** https://cost-aware-inference.onrender.com
>
> The hosted sandbox uses the real gateway, scheduler, cache, quota, failover, accounting, and telemetry paths. AWS/Azure/GCP responses and provider price/latency inputs are intentionally simulated so the demo can stay publicly accessible without GPU spend.

---

## What this project demonstrates

- Cost-aware routing across AWS, Azure, and GCP-style inference targets
- Weighted provider scoring using cost, latency, utilization, and model quality
- Hard filters for cloud allowlists, privacy/trust, budget, health, and request constraints
- Automatic failover with bounded retries and circuit breakers
- Redis-backed caching, quotas, shared state, leases, and provider signals
- Per-request cost accounting based on configured pricing and token usage
- Sensitive-request routing to trusted providers only
- Kafka/Redpanda-backed asynchronous jobs
- Prometheus metrics and Grafana dashboards
- OpenAI-compatible vLLM serving targets
- Docker Compose, Render, Helm, and Terraform deployment assets

---

## Live interactive demo

### [Open the public sandbox →](https://cost-aware-inference.onrender.com)

The browser playground lets you choose eligible clouds, simulate provider outages, change output limits, enable or disable exact caching, mark requests as sensitive, and inspect the resulting routing decision.

For each request the dashboard shows:

- selected cloud and provider
- provider attempt path
- cache result
- estimated and reserved cost
- prompt/output token usage
- round-trip time
- provider health and routing weights
- connected runtime services

### Good demo prompts

```text
Explain why a cost-aware router might choose a slightly slower cloud provider for an AI inference request.
```

```text
Describe the trade-off between minimizing inference latency and minimizing cloud cost.
```

```text
Explain circuit breakers and failover in a distributed inference platform in simple terms.
```

Useful experiments:

- Run the same prompt twice with **Exact cache** enabled.
- Simulate an outage for the provider that would normally win.
- Enable **Sensitive request** and observe trusted-provider routing.
- Disable one or more clouds and inspect how the candidate set changes.

---

## Architecture

```mermaid
flowchart TB
    U[Browser / API Client]
    G[FastAPI Gateway]
    Q[Quota + Policy Admission]
    C[Redis Cache / Shared State]
    R[Weighted Router]

    U --> G
    G --> Q
    Q --> C
    Q --> R

    subgraph PROVIDERS[Inference Provider Pool]
        direction LR
        A[AWS Target]
        Z[Azure Target]
        X[GCP Target]
    end

    R --> A
    R --> Z
    R --> X

    A --> O[Cost + Metrics + Traces]
    Z --> O
    X --> O

    O --> P[Prometheus]
    P --> D[Grafana]

    G -. Async jobs .-> K[Kafka / Redpanda]
    S[Pricing / Health / Utilization Signals] --> K
    K --> W[Async Workers]
    W --> R
    K --> C
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

Public sandbox weights:

| Signal | Weight |
| --- | ---: |
| Cost | 55% |
| Latency | 25% |
| Utilization | 15% |
| Quality | 5% |

Lower score wins after hard policy filters are applied.

---

# Run locally

## Option 1 — Public dashboard

### Requirements

- Python **3.12+**
- Git

No cloud account, GPU, Redis, Kafka, or Docker is required for this mode.

### 1. Clone

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

### 4. Start the sandbox

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

Open:

```text
http://127.0.0.1:8000
```

API docs:

```text
http://127.0.0.1:8000/docs
```

The sandbox automatically generates ephemeral internal demo credentials when none are supplied.

---

## Option 2 — Original local API demo

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.lock
python scripts/run_demo.py
```

Then from another terminal:

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H 'Authorization: Bearer local-demo-key-change-me' \
  -H 'Content-Type: application/json' \
  -d '{"model":"small","messages":[{"role":"user","content":"Explain why caching can reduce inference cost"}]}'
```

Optional checks:

```bash
python scripts/smoke.py
python scripts/benchmark.py --requests 10000 --concurrency 32
```

The benchmark uses local mock providers; it is not a real GPU/cloud cost benchmark.

---

## Option 3 — Full local platform with Docker

The Compose stack includes the gateway, worker, provider-signal publisher, three mock providers, Redis, Redpanda/Kafka, Prometheus, and Grafana.

```bash
cp .env.example .env
docker compose up --build -d
python scripts/smoke.py
```

Useful endpoints:

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

Delete demo Redis/Kafka volumes too:

```bash
docker compose down -v
```

---

## Public API example

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

The public sandbox applies request-size, token, deadline, and per-IP rate limits.

For the authenticated API and more examples, see [`docs/API.md`](docs/API.md).

---

## Core capabilities

| Capability | Implementation |
| --- | --- |
| Gateway | FastAPI, request validation, API-key auth, model aliases |
| Routing | Weighted cost / latency / utilization / quality scheduler |
| Policy | Cloud allowlists, privacy trust, health, deadline and budget filters |
| Reliability | Timeouts, bounded concurrency, circuit breakers and failover |
| Cache | Tenant-isolated exact cache and request coalescing |
| Semantic cache | Optional embedding-based similarity reuse |
| Quotas | Request/token limits and daily cost reservation |
| Privacy | Sensitive requests restricted to trusted providers |
| Async jobs | Kafka jobs, idempotency, workers and result deduplication |
| Live signals | Pricing / health / utilization events with Redis snapshots |
| Observability | Prometheus, Grafana and optional OTLP traces |
| Serving | OpenAI-compatible vLLM target |
| Infrastructure | Docker Compose, Render, Helm and Terraform |

---

## Configuration

`CONFIG_PATH` selects the runtime YAML configuration.

| File | Purpose |
| --- | --- |
| `config/public-demo.yaml` | Browser sandbox with simulated cloud providers |
| `config/demo.yaml` | Lightweight local mock demo |
| `config/compose.yaml` | Full Docker Compose environment |
| `config/production.example.yaml` | Template for real OpenAI-compatible provider endpoints |

Important environment variables:

```text
CONFIG_PATH
REDIS_URL
KAFKA_BOOTSTRAP_SERVERS
PUBLIC_DEMO_ENABLED
```

Do not use the public-demo configuration for customer traffic.

---

## Real cloud deployment model

```text
                   FastAPI Gateway
                         │
                   Weighted Router
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
            AWS        Azure       GCP
            vLLM       vLLM        vLLM
              └──────────┼──────────┘
                         │
                 Redis + Kafka
                         │
              Prometheus / Grafana
```

The repository includes Helm and Terraform assets for this model. The public Render sandbox intentionally uses simulated providers rather than always-on GPU instances.

---

## Deploy on Render

[`render.yaml`](render.yaml) defines the public web service and Redis-compatible Render Key Value store.

Hosted deployment:

### https://cost-aware-inference.onrender.com

---

## Testing

```bash
ruff check .
ruff format --check .
python -m pytest -q
```

With a local Redis instance:

```bash
TEST_REDIS_URL=redis://localhost:6379/15 python -m pytest tests/test_redis_integration.py -q
```

See [`docs/VALIDATION.md`](docs/VALIDATION.md) for validation scope and evidence.

---

## Repository structure

```text
cost-aware-inference/
├── inference/          # gateway, router, cache, jobs, workers and telemetry
├── web/                # public interactive dashboard
├── config/             # runtime configuration profiles
├── tests/              # unit, API, concurrency and integration tests
├── scripts/            # demo launcher, smoke tests and load generation
├── deploy/             # Helm charts and Terraform infrastructure
├── observability/      # Prometheus and Grafana configuration
├── docs/               # architecture, API, deployment and operations docs
├── compose.yaml
├── render.yaml
└── README.md
```

---

## Design docs

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/API.md`](docs/API.md)
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)
- [`docs/RUNBOOK.md`](docs/RUNBOOK.md)
- [`docs/VALIDATION.md`](docs/VALIDATION.md)
- [`SECURITY.md`](SECURITY.md)
- [`CONTRIBUTING.md`](CONTRIBUTING.md)

---

## Scope and transparency

The hosted demo demonstrates the **control plane**. Gateway handling, routing, cache behavior, quotas, failover, Redis state, circuit breakers, and estimated-cost accounting are real project code paths.

The provider responses, latency inputs, utilization values, and provider pricing snapshots are simulated. The public sandbox is not presented as a measured AWS/Azure/GCP GPU benchmark.

---

## Contributing

Contributions, bug reports, and design discussions are welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a pull request.

Choose an open-source license before broad redistribution or contribution if the repository is made public.
