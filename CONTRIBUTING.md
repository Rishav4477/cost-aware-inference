# Contributing

Use Python 3.12 and install `requirements-dev.lock`. Run `ruff check .`, `ruff format --check .`, and `python -m pytest -q` before opening a pull request. Run the HTTP smoke test for gateway changes. Redis/Kafka behavior changes should pass the Compose CI job and add a failure-oriented regression test.

Keep pull requests focused. Explain the problem, behavior changed, tradeoffs, and validation actually performed. Do not claim cloud savings, model accuracy, failover SLAs or throughput from mock-only tests. Do not manufacture commits, contribution counts or benchmarks. Preserve tenant isolation and privacy constraints in any new routing/caching implementation.

Provider additions must document authentication, request/response schemas, timeout behavior, usage accounting and test coverage. Changes to job/cache envelopes require an explicit versioning/migration plan. Never include credentials, personal data or generated runtime state.

The repository remains private during initial development. The owner will select a license before accepting public contributions or announcing an open-source release. No open-source license is implied by these contribution instructions.
