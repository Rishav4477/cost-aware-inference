# Initial design decisions

| Decision | Why | Cost or limitation |
| --- | --- | --- |
| Python/FastAPI gateway | Matches the recorded project scope, straightforward async HTTP and validation | Profile before adding a Go gateway; avoid two languages without a measured need |
| vLLM-compatible endpoints across clouds | Same inference protocol across hosting providers | Native Bedrock/Vertex/Azure OpenAI adapters are separate future work |
| Operator-fed effective token prices | Makes cost signals comparable and testable | Does not discover GPU prices or reconcile cloud invoices automatically |
| Redis Lua admission | Atomic tenant limits across gateway replicas | Redis durability/availability becomes part of admission correctness |
| Reserve all potential attempt estimates | Failed/timeout calls can still be billed | Conservative reservations may reject otherwise affordable traffic |
| Exact cache by default | Predictable response reuse with tenant/policy isolation | Reduced hit rate compared with approximate matching |
| Semantic cache opt-in | Real embedding-based reuse without false precision | Similarity is approximate; external embeddings add latency/cost |
| Kafka ids + Redis job payload | Small broker envelopes and tenant-owned result lookup | At-least-once execution; Redis is required for payload/result durability |
| Existing GPU clusters in Terraform | Portable serving module without assuming account/network ownership | Cluster provisioning and inter-cloud network setup remain operator prerequisites |
| Grafana dashboard | Standard operational view from real metrics | No custom admin web app or self-service tenant UI in initial release |
| Single implementation commit | Honest initial build history | Contribution counts grow through actual reviewed changes |
