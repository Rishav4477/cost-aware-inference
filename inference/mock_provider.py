"""Deterministic local mock. This is not an ML model or a cloud endpoint."""

import asyncio
import os
import time
import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Demo inference provider")
state = {"healthy": True, "delay_ms": int(os.getenv("MOCK_DELAY_MS", "35"))}


class Fault(BaseModel):
    healthy: bool = True
    delay_ms: int = Field(default=35, ge=0, le=120000)


@app.post("/demo/fault")
async def fault(body: Fault):
    state.update(body.model_dump())
    return state


@app.get("/healthz")
async def health():
    if not state["healthy"]:
        raise HTTPException(503, "Simulated outage")
    return state


@app.post("/v1/chat/completions")
async def chat(body: dict):
    await asyncio.sleep(state["delay_ms"] / 1000)
    if not state["healthy"]:
        raise HTTPException(503, "Simulated outage")
    content = "[DEMO: no model invoked] " + body["messages"][-1]["content"][:100]
    prompt_tokens = sum(len(m["content"].encode()) for m in body["messages"])
    output_tokens = min(body["max_tokens"], len(content.encode()))
    return {
        "id": "mock-" + uuid.uuid4().hex,
        "created": int(time.time()),
        "object": "chat.completion",
        "model": body["model"],
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": prompt_tokens + output_tokens,
        },
    }


@app.get("/v1/models")
async def models():
    await health()
    return {"object": "list", "data": [{"id": "demo-model", "object": "model"}]}
