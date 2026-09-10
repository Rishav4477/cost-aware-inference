"""Exercise routing, caching, outage failover, privacy and async jobs over HTTP."""

import asyncio
import os

import httpx


async def main():
    headers = {"Authorization": "Bearer " + os.getenv("DEMO_API_KEY", "local-demo-key-change-me")}
    body = {"messages": [{"role": "user", "content": "smoke-test"}]}
    async with httpx.AsyncClient(
        trust_env=False, base_url="http://127.0.0.1:8000", headers=headers, timeout=10
    ) as c:
        for port in (8101, 8102, 8103):
            await c.post(f"http://127.0.0.1:{port}/demo/fault", json={"healthy": True})
        first = await c.post("/v1/chat/completions", json=body)
        assert first.status_code == 200, first.text
        hit = await c.post("/v1/chat/completions", json=body)
        assert hit.json()["routing"]["cache_hit"] == "exact", hit.text
        try:
            await c.post("http://127.0.0.1:8101/demo/fault", json={"healthy": False})
            failover = await c.post("/v1/chat/completions", json={**body, "cache": "off"})
            assert failover.status_code == 200, failover.text
            assert failover.json()["routing"]["provider"] != "aws-demo", failover.text
            sensitive = await c.post("/v1/chat/completions", json={**body, "sensitive": True})
            assert sensitive.json()["routing"]["provider"] == "gcp-demo", sensitive.text
            print("Outage failover:", failover.json()["routing"])
        finally:
            await c.post("http://127.0.0.1:8101/demo/fault", json={"healthy": True})
        job = await c.post("/v1/jobs", json=body, headers={"Idempotency-Key": "smoke-job"})
        assert job.status_code == 202, job.text
        for _ in range(100):
            result = await c.get("/v1/jobs/" + job.json()["id"])
            if result.json()["status"] in ("completed", "failed"):
                break
            await asyncio.sleep(0.1)
        assert result.json()["status"] == "completed", result.text
        print(
            "PASS: authentication, inference, caching, outage failover, privacy routing, async completion"
        )


if __name__ == "__main__":
    asyncio.run(main())
