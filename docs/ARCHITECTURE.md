# Architecture and engineering decisions

## Admission and routing

Authentication maps a secret API key to a tenant; clients cannot select their own tenant id. A fixed-minute Redis Lua transaction admits request and conservative token counts atomically. UTC daily budget accounting uses a second atomic reservation. Invalid requests are rejected before inference.

Candidates must expose the requested logical model, satisfy allowed-cloud policy, and be trusted when `sensitive=true`. Open circuits and unavailable/freshness-invalid providers are filtered. A configured or live price estimate, utilization ceiling, and predicted latency further constrain eligibility. Hard policies are never relaxed during failover.

The score is `cost_weight * cost/max_cost + latency_weight * latency/max_latency + utilization_weight * utilization + quality_weight * (1-quality)`. Lowest score wins; provider id breaks ties. Values are normalized among eligible candidates. Quality is an operator-supplied score, not a model evaluation system. Clients choose a model alias; there is no hidden prompt-complexity classifier.

Each provider is attempted once, in score order. A shared HTTP client pools connections. Concurrency is bounded per provider per process. Timeouts bound waiting and HTTP execution. Circuit failures suppress a provider for a cooldown; traffic can probe again afterward. This is a simple process-local breaker, not a globally coordinated half-open probe. Shared Kafka health snapshots allow faster exclusion across replicas.

## Cost semantics

Token admission estimates prompt size by UTF-8 byte length plus framing allowance and reserves requested output tokens. It is conservative for common tokenizers, but not a universal tokenizer-specific upper bound. The per-request cost limit constrains **estimates**, not an enforceable invoice ceiling. The gateway reserves the sum of candidate attempt estimates before calling any backend; if all failover reservations exceed the request budget it attempts only the top candidate.

Reservations include potentially billed failed attempts and are never refunded. This can reject requests earlier than necessary, but avoids treating timeout as proof of zero billing. Actual successful-response cost estimates use backend token usage and the input/output prices captured during scheduling. Failed-attempt billing, idle GPU time, cache/embedding charges, networking, control-plane costs and billing reconciliation are not included in that metric. Reservations reset at UTC midnight; token/request windows are fixed UTC minutes, not rolling windows.

Prices in demo files are synthetic. Real self-hosted GPU hourly prices must be translated by the operator into effective token prices using throughput and utilization, then fed through signals. The included publisher probes `/v1/models` and forwards configured prices/utilization: it is a working health publisher, not a cloud price scraper. Its latency is health-probe latency, not inference latency. Replace this field with your inference EWMA for useful latency-aware production scheduling.

## Cache and privacy

Exact keys include the provider/embedding configuration revision, tenant id and the complete validated request, including model, privacy, allowed clouds, deadline and cost policy. Nonzero temperature, `cache=off`, and sensitive requests bypass all caches. A distributed Redis lease coalesces identical deterministic work across replicas. A failed lease holder allows a subsequent attempt; coalescing is best effort, not exactly-once execution.

Semantic reuse additionally needs one user message, zero temperature, explicit `cache=semantic`, and a configured embedding service. A bounded 100-entry per-policy Redis list stores embeddings and responses for cosine comparison. It keeps actual expiry timestamps so old entries do not live forever under list renewal. Sensitive prompts never reach that service. Similarity is not semantic equivalence: restrict this feature to workloads where answer reuse is acceptable. There is no claim of a measured false-hit rate.

The cache stores responses, not raw prompts, but outputs and embeddings may still contain sensitive data. Tenant ownership and policy partitioning are mandatory. The trust flag is configured by the operator; it does not automatically prove a cloud region, network, or provider complies with a data-handling requirement.

## Durable jobs and failure windows

Job ids are a digest of tenant and Idempotency-Key. A fingerprint prevents reusing a key with different input. Redis stores payload/status for 24 hours, and the Kafka envelope contains only the job id. A producer acknowledgement is required before returning 202. If delivery or acknowledgement is ambiguous, the client can retry the same key; duplicate envelopes are safe after terminal state persistence.

The worker obtains a 130-second lease, executes within the request's maximum 120-second deadline, writes terminal state, and only then commits the Kafka offset. Raw job prompts are removed from terminal state. Infrastructure exceptions stop processing without committing so the supervisor can restart and redeliver. Invalid envelopes are logged by topic/offset and discarded without logging payloads. Failed inference ends the job as failed; submit a new key to explicitly retry.

This is **at-least-once**, not exactly-once. A crash after the provider has responded but before Redis persists the result can trigger duplicate inference and budget reservation. Long stalls or expired leases can also duplicate work. A gateway crash before enqueue acknowledgement can leave an unaccepted orphan that expires in Redis; it is not silently accepted. Redis and Kafka persistence are required for durability; the local in-memory mode cannot provide it. Jobs can expire after 24 hours; operate queue lag well below that limit.

## Deployment boundary

Terraform deploys vLLM charts into existing EKS/AKS/GKE contexts. It does not provision accounts, networks, GPU node pools, managed Kafka/Redis, or private inter-cloud connectivity. Kubernetes internal DNS names are not routable between clouds: configure gateway endpoint URLs using private routing/VPN and authenticated TLS ingress. Gateway and vLLM charts intentionally expose ClusterIP services only.

vLLM performs continuous batching inside the model server; the gateway does not combine unrelated prompts into one request. The gateway Helm HPA uses CPU; GPU autoscaling and zero-to-one model startup need separate operational policies. The initial vLLM chart uses one RWO model-cache volume and a Recreate deployment; keep one replica per release or install independent releases for additional replicas.

Prometheus counters on gateway and worker capture completed inference attempts and cost estimates. Each worker exposes metrics on port 8001; the gateway uses 8000. Labels avoid prompt content, API keys, raw tenant ids, and request ids. OTLP spans contain provider ids only. Cloud tracing export requires an operator-configured collector.
