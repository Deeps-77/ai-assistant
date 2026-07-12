"""HTTP server exposing the delivery assistant.

Mirrors the existing batch ``/run`` endpoint in :mod:`main` but drives the
interactive assistant instead. When a human-in-the-loop approval is required the
request pauses and returns the interrupt payload (HTTP 202) so a client can
approve and resume via ``/resume``.
"""

from __future__ import annotations

import argparse
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from assistant.app import build_assistant
from assistant.config import resolve_assistant_config

# Shared across requests so a paused ``/run`` can be resumed by a later
# ``/resume`` (each request rebuilds the agent, but they must share checkpoints).
_CHECKPOINTER = InMemorySaver()


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None
    project_path: str | None = None


class ResumeRequest(BaseModel):
    thread_id: str
    decisions: list[dict]


def create_app() -> FastAPI:
    app = FastAPI(title="AI Software Delivery Assistant")

    @app.post("/run")
    async def run(req: ChatRequest):
        cfg = resolve_assistant_config(req.project_path)
        agent = build_assistant(cfg=cfg, checkpointer=_CHECKPOINTER)
        thread_id = req.thread_id or f"srv-{uuid.uuid4().hex[:8]}"
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 400}

        result = agent.invoke({"messages": [("user", req.message)]}, config=config)
        interrupts = result.get("__interrupt__") or result.get("__interrupts__")
        if interrupts:
            value = getattr(interrupts[0], "value", interrupts[0])
            return JSONResponse(
                status_code=202,
                content={"status": "paused", "thread_id": thread_id, "interrupts": [value]},
            )

        messages = result.get("messages", [])
        reply = messages[-1].content if messages else ""
        return {"status": "done", "thread_id": thread_id, "reply": reply}

    @app.post("/resume")
    async def resume(req: ResumeRequest):
        cfg = resolve_assistant_config()
        agent = build_assistant(cfg=cfg, checkpointer=_CHECKPOINTER)
        config = {"configurable": {"thread_id": req.thread_id}, "recursion_limit": 400}
        result = agent.invoke(Command(resume={"decisions": req.decisions}), config=config)
        interrupts = result.get("__interrupt__") or result.get("__interrupts__")
        if interrupts:
            value = getattr(interrupts[0], "value", interrupts[0])
            return JSONResponse(
                status_code=202,
                content={"status": "paused", "thread_id": req.thread_id, "interrupts": [value]},
            )
        messages = result.get("messages", [])
        reply = messages[-1].content if messages else ""
        return {"status": "done", "thread_id": req.thread_id, "reply": reply}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="Serve the delivery assistant over HTTP")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--project-path", help="Project root to operate on")
    args = parser.parse_args()

    if args.project_path:
        import os
        os.environ["ASSISTANT_PROJECT_PATH"] = args.project_path

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
