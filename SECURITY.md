# Security and data handling

The default demo key and mock fault endpoints are only for loopback development. Use generated secrets, trusted TLS ingress and private network access for real workloads. Never commit `.env`, private keys, Terraform state, cloud credentials or kubeconfig. The private repository visibility must be verified before uploading code.

Tenant identity comes from the API key mapping. Cache keys and job ids include tenant identity; a caller cannot read another tenant's job. Keys use constant-time comparison, request bodies are bounded, and invalid/unsupported fields are rejected. Metrics omit raw prompts, API keys, raw tenant ids and request ids. Check your reverse proxy, model server, collector and broker logs separately: the gateway cannot control those systems' logging.

`sensitive:true` restricts inference to operator-designated trusted providers and bypasses caching, embeddings and asynchronous persistence. It is an explicit caller declaration, not PII detection or a compliance certification. Configure trust and region/network constraints carefully; do not mark an unreviewed third-party endpoint trusted.

Ordinary exact cache entries retain responses. Semantic entries retain embeddings and responses. Jobs retain prompts until terminal state or expiry, and retain results for 24 hours. Redis persistence/backups can retain records beyond logical TTL; apply an appropriate storage retention policy. Semantic reuse is approximate and opt-in, suitable only where potentially different wording can safely reuse an answer.

Quotas are conservative application estimates, not hard cloud invoice guarantees. Failed attempts may still be billed. State-store errors fail closed. Circuit state and semaphores are local to a process. Protect pricing/health Kafka topics with ACLs; only trusted publishers may send events. Use Redis authentication/TLS and Kafka SASL_SSL for remote services.

This initial repository is not a penetration-tested product. Before public launch, conduct a security review of deployment networking, secret rotation, dependency images, tenant provisioning, abuse controls and model-serving logs. Report a vulnerability privately to the repository owner; do not include secrets or customer prompts in a public issue.
