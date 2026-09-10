# Deployment

## Local development and Compose

Use the README commands. All compose images are pinned to explicit versions; validate security and compatibility before promotion. The development broker is single-node and uses plaintext on the internal Docker network. Redis uses AOF/noeviction; disk exhaustion is an operational failure, not a reason to evict quota/job records.

## Real model endpoints

The gateway speaks the non-streaming OpenAI-compatible `/v1/chat/completions` contract. Serve the same model or intentionally equivalent models under one logical alias. Each response must include nonnegative integer `prompt_tokens` and `completion_tokens`. Configure provider-specific credentials via the `api_key_env` name in YAML.

A local GPU example:

```bash
# Set a generated secret in the current shell first.
export VLLM_API_KEY

docker run --rm --gpus all -p 127.0.0.1:8200:8000 \
  -e VLLM_API_KEY -v model-cache:/root/.cache/huggingface \
  vllm/vllm-openai:v0.19.1 \
  --model Qwen/Qwen2.5-0.5B-Instruct --max-model-len 4096
```

Configure a provider `base_url: http://127.0.0.1:8200/v1`, `api_key_env: VLLM_API_KEY`, the exact served model name, and an alias. Model downloading and GPU execution require your own runtime; this was not executed in the implementation environment. vLLM continuous batching and the OpenAI-compatible interface are described in the [official documentation](https://docs.vllm.ai/en/v0.19.1/serving/openai_compatible_server/); environment-based authentication is documented under [VLLM_API_KEY](https://docs.vllm.ai/en/stable/configuration/env_vars/).

## EKS, AKS and GKE serving releases

Prerequisites: existing GPU clusters and kubeconfig contexts, NVIDIA device plugin/drivers, a default storage class, model download access, and nodes labeled `inference-pool=gpu`. Choose GPU types and quotas appropriate for your model. The small default model is for a modest validation deployment.

In each target cluster create namespace `inference` and a secret `vllm-secrets` containing `api-key` using your organization's secret manager or `kubectl create secret --from-file`. Do not put keys into Terraform variables or tracked YAML.

```bash
cd deploy/terraform/environments
cp terraform.tfvars.example terraform.tfvars
# Edit absolute kubeconfig path and all three actual context names.
terraform init
terraform plan
# Apply only after reviewing the plan in your cloud environment.
terraform apply
```

The reusable `modules/serving` module installs the same vLLM Helm chart into the three provided contexts. It uses the [Helm provider](https://registry.terraform.io/providers/hashicorp/helm/2.17.0/docs/resources/release). It does not create clusters, GPU pools, networks, DNS, TLS ingress or cloud accounts. Terraform outputs cluster-local service addresses, which require inter-cloud routing/TLS ingress before a remote gateway can use them. Preserve Terraform state securely; never commit it.

For the initial RWO/Recreate model-cache chart keep `replicas: 1`. Scale with additional independent releases rather than sharing that PVC across nodes. vLLM's image and cluster security policy must be validated together on the target GPU nodes.

## Gateway deployment

1. Build the image and push it to your private registry.
2. Provision Redis with persistence/HA and Kafka with retained topics `inference.jobs` (e.g. 6 partitions) and `inference.signals` (e.g. 3 partitions). Use replication appropriate to the broker cluster. Set job retention and processing capacity to keep backlog below 24 hours.
3. Create a Kubernetes Secret containing `PRIMARY_API_KEY`, the three model API keys, and any Kafka authentication settings. Each tenant key must be unique and at least 16 characters.
4. Copy `config/production.example.yaml` outside version control; replace URLs and prices. Keep `demo:false` and `require_signals:true`. Populate provider `trusted` flags only after verifying the real hosting/privacy boundary.
5. Label inference GPU nodes, configure private inter-cloud connectivity, and create authenticated TLS ingress for model endpoints. Cluster-local DNS alone is insufficient across clouds.
6. Install gateway chart into the control cluster:

```bash
helm upgrade --install inference deploy/helm/inference \
  --namespace inference --create-namespace \
  --set image.repository=YOUR_PRIVATE_IMAGE \
  --set image.tag=YOUR_VERSION \
  --set existingSecret=inference-secrets \
  --set redisUrl=rediss://YOUR_REDIS:6379/0 \
  --set kafkaBootstrap=YOUR_KAFKA:9092 \
  --set-file config=/absolute/path/production.yaml
```

Chart deployments include gateway, worker, and signal publisher. HPA requires metrics-server. Images must be accessible to nodes through your registry credentials/workload identity. The chart mounts secrets as environment variables, runs gateway components as non-root, uses a read-only root filesystem, and disables Kubernetes API tokens. Configure ingress, TLS, network policies and monitoring scrape discovery for your cluster. Restrict `/metrics`, `/docs`, `/openapi.json`, and operational routes at external ingress. One Uvicorn process per pod preserves metric correctness.

Worker metrics are on port 8001; gateway metrics are on port 8000. Configure Prometheus pod discovery or internal services to scrape each instance, not one load-balanced service when aggregating counters. The included compose dashboard sums instance series.

## Signals, Kafka security and tracing

The supplied publisher forwards configured prices/utilization and measured `/models` health-probe latency every cycle. For production replace those fields with observed inference latency/utilization and normalized pricing from your own billing feeds. A `Signal` event contains `provider_id`, epoch-seconds `timestamp`, `healthy`, `latency_ms`, `utilization`, `input_usd_per_million`, and `output_usd_per_million`. NaN/inf, unknown ids, stale/future timestamps, and out-of-order replacement are rejected. Freshness-required routing fails closed if the signal pipeline stops.

All Kafka components accept `KAFKA_SECURITY_PROTOCOL` (`PLAINTEXT`, `SSL`, `SASL_PLAINTEXT`, `SASL_SSL`), optional `KAFKA_CA_FILE`, `KAFKA_SASL_MECHANISM` (default SCRAM-SHA-512), `KAFKA_USERNAME`, and `KAFKA_PASSWORD`. TLS verifies certificates. Use SASL_SSL for authenticated remote brokers; mount any custom CA file separately. Grant topic-specific broker ACLs: unauthorized pricing events could influence routing.

For tracing set `OTEL_EXPORTER_OTLP_ENDPOINT` for an HTTP OTLP collector. Traces contain provider ids and timings, not prompts. Configure collector authentication/transport through standard OTLP environment settings. The chart can receive these values through its existing Secret.

## Before production traffic

Run CI and a real-model canary on each cloud, tune attempt deadlines and concurrency, replace synthetic prices, test shared-state/broker outages and recovery, validate secret rotation, and reconcile cost estimates against billing. The local mock benchmark does not replace these checks. No cloud deployment or billable resources were created during this build.
