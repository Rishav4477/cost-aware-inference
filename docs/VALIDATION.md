# Validation evidence

Validation date: 2026-09-10. Runtime: Python 3.12 on Linux x86_64.

| Check | Result |
| --- | --- |
| Ruff lint and format | Passed |
| Automated tests including real Redis 7.4.2 | 38 passed, 0 skipped |
| Real-Redis atomic budgets/request limits | Passed |
| Two independent gateway instances sharing Redis/cache leases | Passed; 20 concurrent identical requests caused one upstream call |
| HTTP smoke test against three local mock servers | Passed: inference, exact cache, simulated outage failover, sensitive routing, async completion |
| 10,000-request HTTP load run, concurrency 32 | 10,000 successes; 0 errors; p95 108.96 ms; 379.15 requests/sec |
| Gateway Helm chart | Lint passed; rendered seven valid YAML resources |
| vLLM Helm chart | Lint passed; rendered three valid YAML resources |
| Terraform formatting | Passed |
| Terraform full validation | Not completed: Helm provider binary failed its plugin startup handshake in this runtime |
| Compose YAML | Parsed; 11 services |
| Full Docker Compose/Kafka execution | Not run locally; Docker is unavailable. CI workflow supplied |
| Actual vLLM GPU inference | Not run; no GPU model server attached |
| Cloud deployment / inter-cloud failover | Not run; no cloud infrastructure or credentials supplied |
| GitHub Actions | See the repository Actions tab for remote validation results |

## Load-test interpretation

See `benchmark-local.json` for raw measurements. The load run followed a smoke-test outage drill, so early traffic used Azure/GCP mock backups while the AWS mock circuit recovered. The test used cache disabled and synthetic configured prices. All providers were local mock HTTP servers, with a nominal 35 ms artificial delay; no real LLM or cloud provider was invoked. Reported latency includes HTTP, queueing, gateway work and mock delay. It is not isolated scheduling overhead or model throughput.

The recorded successful-inference cost estimate is derived from illustrative prices. It is not a cloud bill, total infrastructure spend, or evidence of a 35% cost reduction. No cloud uptime or failover SLA is inferred from this test. The benchmark preceded non-routing changes to Kafka TLS options, worker metrics, and cache configuration revision namespacing; the complete 38-test suite ran after those changes.

## Reproduce

```bash
python -m pytest -q
# With a disposable real Redis instance:
TEST_REDIS_URL=redis://localhost:6379/15 python -m pytest -q
# In two terminals:
python scripts/run_demo.py
python scripts/smoke.py
python scripts/benchmark.py --requests 10000 --concurrency 32
```

Helm commands used version 3.17.3. Terraform formatting used version 1.11.4. Cloud tests, Compose/Kafka recovery drills and Terraform full validation remain required before a production deployment.
