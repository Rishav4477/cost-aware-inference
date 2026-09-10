import asyncio

import httpx
import pytest
from conftest import response

from inference.app import create_app
from inference.store import MemoryStore


@pytest.fixture
async def api(cfg):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: response())) as upstream:
        app = create_app(cfg, MemoryStore(), upstream)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                yield client


BODY = {"messages": [{"role": "user", "content": "hello"}]}
AUTH = {"Authorization": "Bearer test-tenant-key-12345"}


async def test_auth_and_validation(api):
    assert (await api.post("/v1/chat/completions", json=BODY)).status_code == 401
    assert (
        await api.post("/v1/chat/completions", headers=AUTH, json={**BODY, "stream": True})
    ).status_code == 422
    result = await api.post("/v1/chat/completions", headers=AUTH, json=BODY)
    assert result.status_code == 200
    assert result.json()["routing"]["provider"] == "cheap"
    assert (await api.get("/readyz")).status_code == 200
    assert "inference_requests_total" in (await api.get("/metrics")).text


async def test_body_size_limit(api):
    assert (
        await api.post("/v1/chat/completions", headers=AUTH, content="x" * 100001)
    ).status_code == 413


async def test_jobs_idempotency_and_completion(api):
    headers = {**AUTH, "Idempotency-Key": "test-one"}
    a = await api.post("/v1/jobs", headers=headers, json=BODY)
    assert a.status_code == 202
    job_id = a.json()["id"]
    for _ in range(50):
        result = (await api.get("/v1/jobs/" + job_id, headers=AUTH)).json()
        if result["status"] == "completed":
            break
        await asyncio.sleep(0.01)
    assert result["status"] == "completed"
    b = await api.post("/v1/jobs", headers=headers, json=BODY)
    assert b.json()["id"] == job_id
    assert b.json()["status"] == "completed"
    assert (
        await api.post("/v1/jobs", headers=headers, json={**BODY, "max_tokens": 50})
    ).status_code == 409
    assert "request" not in result


async def test_sensitive_job_rejected(api):
    r = await api.post(
        "/v1/jobs",
        headers={**AUTH, "Idempotency-Key": "sensitive"},
        json={**BODY, "sensitive": True},
    )
    assert r.status_code == 400


async def test_unknown_job(api):
    assert (await api.get("/v1/jobs/job-missing", headers=AUTH)).status_code == 404
