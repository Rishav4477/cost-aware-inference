# API

Use `Authorization: Bearer <tenant-key>` for all `/v1` routes. `/healthz`, `/readyz`, and `/metrics` are operational endpoints and should remain internal. `/docs` and `/openapi.json` expose the generated contract.

## Synchronous completion

```bash
curl http://localhost:8000/v1/chat/completions \
  -H 'Authorization: Bearer local-demo-key-change-me' \
  -H 'Content-Type: application/json' \
  -d '{
    "model":"small",
    "messages":[{"role":"user","content":"Explain a circuit breaker"}],
    "max_tokens":128,
    "temperature":0,
    "allowed_clouds":["aws","gcp"],
    "max_cost_usd":0.01,
    "deadline_ms":10000,
    "cache":"exact",
    "sensitive":false
  }'
```

The response follows a non-streaming chat-completion shape with `choices`, `usage`, and a `routing` extension containing `provider`, `cloud`, attempted provider ids, cache hit kind, successful inference cost estimate, and reserved cost estimate. Cached responses have zero current inference cost but retain original token usage and reservation metadata for provenance. Cost reservations are estimates, not billing guarantees.

For private data use `sensitive:true`. The request is constrained to trusted providers; caching and embedding are bypassed even if requested. Combining this with `allowed_clouds` that excludes all trusted providers returns 503.

`stream:true`, tool calls, arbitrary extra fields, and multimodal content are rejected with 422. Supported roles are system, user, assistant. Total message content is limited to 64KB UTF-8, each message to 32,000 characters, and the HTTP body to 100,000 bytes. `max_tokens` is 1–4096 and the overall request deadline is 100–120,000 ms.

## Async jobs

```bash
curl http://localhost:8000/v1/jobs \
  -H 'Authorization: Bearer local-demo-key-change-me' \
  -H 'Idempotency-Key: my-batch-item-001' \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Explain routing"}]}'

curl http://localhost:8000/v1/jobs/JOB_ID \
  -H 'Authorization: Bearer local-demo-key-change-me'
```

POST returns 202 with `id`, `status`, `result`, `error`. Status is queued, completed, or failed. Poll until terminal. The id is stable for a tenant/key within the 24-hour retention window; changing the payload for that key returns 409. Another tenant cannot read the job. Sensitive jobs are rejected because jobs persist payloads. Submission and subsequent worker execution each consume one request allowance; tokens and budget are charged at execution. Kafka mode uses durable storage; local demo jobs are process-local.

If POST returns 503 for a queue issue, retry **the same** Idempotency-Key to recover an ambiguous acknowledgement. After a terminal inference failure, choose a new key to request a new attempt. Retention expiry allows reuse and a new execution.

## Error codes

| Status | Meaning |
| --- | --- |
| 400 | Sensitive async request |
| 401 | Missing/invalid key |
| 404 | Missing job or job belongs to another tenant |
| 409 | Conflicting payload or concurrent idempotent submission |
| 413 | HTTP request body too large |
| 422 | Unsupported/invalid input |
| 429 | Request, token, or estimated daily budget exhausted |
| 503 | No eligible provider, all attempts failed, or queue unavailable |
| 504 | Overall inference deadline expired |

Unexpected state-store failures fail the operation closed and may return 500; callers should retry with bounded backoff. Do not log request bodies or authorization headers while diagnosing errors.
