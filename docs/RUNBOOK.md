# Operations runbook

| Symptom | Investigation and response |
| --- | --- |
| 401 | Verify the caller uses the tenant key named by `key_env`; rotate through Secret and rolling restart. Never paste keys into logs. |
| 429 | Check fixed-minute request/token limits and daily reservations. Budget includes worst-case failover reservations and is not refunded on timeout. |
| 503 no eligible provider | Check alias, cloud restrictions, trusted flag, cost/deadline filters, full utilization, circuit cooldown and signal age. Do not disable privacy constraints to force a result. |
| 503 all providers failed | Check endpoint reachability, credentials, model name, token-usage response fields, provider attempt counters and timeouts. |
| 504 | Review end-to-end deadline versus provider timeout/queueing; inspect p95 request and scheduler histograms separately. |
| Redis unavailable | Gateway readiness fails; state-dependent requests fail closed. Restore Redis and persistence. Do not switch real traffic to memory mode. |
| Jobs remain queued | Check worker logs, Kafka lag/group assignment, Redis availability and model eligibility. Maximum retention is 24h; expired job ids return 404. |
| Duplicate model invocation | At-least-once retry after crash/lease expiry is possible. Check terminal-result persistence and broker redelivery; do not claim exactly-once billing. |
| Invalid signals | Check timestamps/time synchronization, schema/finite values and provider ids. Signals expire; live-only routing will fail closed. |
| GPU pods pending | Verify GPU quota, drivers/plugin, node labels/tolerations and PVC storage class. Keep one pod per RWO release. |
| HPA inactive | Verify metrics-server and CPU resource requests. Backend GPU autoscaling is separate. |

## Failure drill

Against the local demo only:

```bash
curl -X POST http://127.0.0.1:8101/demo/fault \
  -H 'Content-Type: application/json' -d '{"healthy":false}'
# Send a completion with cache:"off" and examine routing.attempts.
curl -X POST http://127.0.0.1:8101/demo/fault \
  -H 'Content-Type: application/json' -d '{"healthy":true}'
```

The supplied smoke test does this and restores health in `finally`. `/demo/fault` belongs only to the mock image command; the real gateway does not expose it.

To test broker redelivery in Compose, submit a job and restart `worker`; poll the same job id. To test outage behavior, stop one mock service then send uncached requests. To test Redis failure, stop Redis and verify admission fails closed. Restore services after each drill. The CI Compose smoke workflow checks the ordinary queue round trip; extensive crash-window validation is a remaining production gate.

## Upgrade and rollback

Pin and scan image versions. Run CI, then canary one release with synthetic non-sensitive requests. `helm rollback inference PREVIOUS_REVISION -n inference` restores the previous chart revision; restore matching application configuration/secrets independently. This initial release has no relational schema migrations. Do not downgrade into incompatible Redis/Kafka record formats; version envelopes before future breaking changes.

Back up Redis and protect backup access because cached outputs and job payloads can be sensitive. Kafka envelopes hold ids; signal topics hold routing metadata. Deleting Redis loses job results, cache, deduplication and quota state. `docker compose down -v` is destructive and should only be used to reset the local development environment.
