"""Enhanced HTTP server for the AI Software Delivery Assistant.

Endpoints
---------
POST /run            Start a new delivery run (fire & forget, stores result)
POST /resume         Resume a paused run (human-in-the-loop decision)
GET  /stream         Server-Sent Events stream of agent step events for a thread
GET  /history/{id}   Full message + agent step history for a thread
GET  /projects       List all known projects (from ChromaDB)
GET  /threads        List recent threads (from ChromaDB)
GET  /search         Semantic search over generated code
GET  /health         Health check

Architecture: Next.js BFF (port 3000) → this server (port 8000).
CORS is only needed for direct browser access; via BFF it is not required,
but we enable it for development convenience.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from assistant.app import build_assistant
from assistant.config import resolve_assistant_config
from assistant import events as evt

# Lazy-import DB so missing chromadb doesn't crash the server
try:
    from assistant import db as _db
    _HAS_DB = True
except Exception:
    _db = None  # type: ignore
    _HAS_DB = False

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

# Shared checkpointer so /resume can resume threads started by /run
_CHECKPOINTER = InMemorySaver()

# Thread-safe executor for sync LangGraph calls
_EXECUTOR = ThreadPoolExecutor(max_workers=8)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None
    project_path: str | None = None
    plan_mode: bool = False


class ResumeRequest(BaseModel):
    thread_id: str
    decisions: list[dict]


class ProjectRequest(BaseModel):
    project_path: str
    name: str | None = None


# ---------------------------------------------------------------------------
# Agent step collector (injects a thin wrapper around graph streaming)
# ---------------------------------------------------------------------------

# Map of canonical LangGraph node names → friendly agent names
_NODE_TO_AGENT: dict[str, str] = {
    "supervisor": "Supervisor",
    "planner": "Planner",
    "architect": "Architect",
    "quality_gen": "Quality Guide",
    "plan_review": "Plan Review",
    "project_init": "Project Init",
    "dispatcher": "Dispatcher",
    "worker_entry": "Developer",
    "worker_module_planner": "Module Planner",
    "worker_coder": "Coder",
    "worker_reviewer": "Reviewer",
    "worker_fixer": "Fixer",
    "worker_complete": "Module Complete",
    "backend_lead": "Backend Lead",
    "module_planner": "Module Planner",
    "module_coder": "Coder",
    "reviewer": "Reviewer",
    "fixer": "Fixer",
    "complete_module": "Module Complete",
    "human_review": "Human Review",
    "qa": "QA",
    "sandbox_setup": "Sandbox Setup",
    "test_executor": "Tester",
    "test_fixer": "Test Fixer",
    "file_writer": "File Writer",
    "delivery": "Manager",
    "analysis_report": "Analysis Report",
    "project_reader": "Project Reader",
    "project_analyzer": "Project Analyzer",
}


def _collect_agent_steps(result: dict[str, Any], thread_id: str) -> list[dict]:
    """Build agent_steps summary from the final state dict."""
    steps = []
    if _HAS_DB:
        steps = _db.get_agent_steps(thread_id)
    if not steps:
        # Reconstruct a minimal steps list from completed_modules
        completed = result.get("completed_modules", []) or []
        if completed:
            steps = [
                {"agent": "Manager", "status": "done",
                 "message": f"Modules completed: {', '.join(completed)}"}
            ]
    return steps


async def _run_agent_async(
    cfg,
    thread_id: str,
    message: str,
    inputs: dict,
    config: dict,
) -> dict:
    """Run the LangGraph agent in a thread and collect SSE events."""
    loop = asyncio.get_event_loop()

    def _run():
        agent = build_assistant(cfg=cfg, checkpointer=_CHECKPOINTER)
        # Stream node-level updates so we can emit SSE events
        collected_steps: list[dict] = []
        result_holder: dict = {}

        try:
            for chunk in agent.stream(inputs, config=config, stream_mode="updates"):
                if not isinstance(chunk, dict):
                    continue
                for node_name, update in chunk.items():
                    if node_name.startswith("__"):
                        # Handle interrupts
                        if node_name == "__interrupt__" and isinstance(update, (list, tuple)):
                            intr = update[0] if update else None
                            value = getattr(intr, "value", intr)
                            interrupts_payload = [value] if value else []
                            evt.emit_paused(thread_id, interrupts_payload)
                            if _HAS_DB:
                                _db.save_thread(thread_id, {
                                    "thread_id": thread_id,
                                    "status": "paused",
                                    "interrupts": interrupts_payload,
                                    "message": message,
                                })
                            return {"__interrupt__": interrupts_payload, "thread_id": thread_id}
                        continue

                    agent_name = _NODE_TO_AGENT.get(node_name, node_name)
                    step_msg = _node_message(node_name, update)
                    step = {
                        "agent": agent_name,
                        "status": "done",
                        "message": step_msg,
                    }
                    collected_steps.append(step)
                    evt.emit_agent_step(thread_id, agent_name, "done", step_msg)
                    if _HAS_DB:
                        _db.append_agent_step(thread_id, agent_name, "done", step_msg)

                    # Update result_holder from state dict updates
                    if isinstance(update, dict):
                        result_holder.update(update)

        except Exception as exc:
            evt.emit_error(thread_id, str(exc))
            if _HAS_DB:
                _db.save_thread(thread_id, {
                    "thread_id": thread_id,
                    "status": "error",
                    "error": str(exc),
                    "message": message,
                })
            return {"error": str(exc), "thread_id": thread_id}

        messages = result_holder.get("messages", [])
        reply = ""
        if messages:
            last = messages[-1]
            reply = last.content if hasattr(last, "content") else str(last)

        evt.emit_done(thread_id, reply, collected_steps)
        if _HAS_DB:
            _db.save_thread(thread_id, {
                "thread_id": thread_id,
                "status": "done",
                "reply": reply,
                "message": message,
                "agent_steps_count": len(collected_steps),
            })

        return {
            "status": "done",
            "thread_id": thread_id,
            "reply": reply,
            "agent_steps": collected_steps,
        }

    return await loop.run_in_executor(_EXECUTOR, _run)


def _node_message(node_name: str, update: dict | Any) -> str:
    """Extract a human-readable message from a node's state update."""
    if not isinstance(update, dict):
        return f"{node_name} completed"
    if "messages" in update:
        msgs = update["messages"]
        if msgs:
            last = msgs[-1]
            content = getattr(last, "content", str(last))
            return content[:200] if content else f"{node_name} completed"
    if "completed_modules" in update:
        return f"Modules completed: {update['completed_modules']}"
    if "delivery_package" in update and update["delivery_package"]:
        return "Delivery package ready"
    if "architecture" in update:
        return "Architecture designed"
    if "stories" in update:
        return f"Planned {len(update.get('modules', []))} modules"
    return f"{node_name} completed"


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Software Delivery Assistant",
        description="Multi-agent SDLC automation platform",
        version="1.0.0",
    )

    # CORS — allow the Next.js dev server and any localhost port
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── /run ────────────────────────────────────────────────────────────────

    @app.post("/run")
    async def run(req: ChatRequest):
        """Start a delivery run. Returns the result synchronously (or 202 if paused)."""
        cfg = resolve_assistant_config(req.project_path)
        if req.plan_mode:
            import os
            os.environ["ASSISTANT_PLAN_MODE"] = "1"

        thread_id = req.thread_id or f"srv-{uuid.uuid4().hex[:8]}"
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 400}

        # Register a queue so /stream can receive events for this thread
        evt.get_or_create_queue(thread_id)

        if _HAS_DB:
            _db.save_thread(thread_id, {
                "thread_id": thread_id,
                "status": "running",
                "message": req.message,
                "project_path": req.project_path or cfg.project_path,
            })
            if req.project_path:
                _db.save_project(req.project_path, {
                    "project_path": req.project_path,
                    "thread_id": thread_id,
                    "name": req.project_path.split("/")[-1].split("\\")[-1],
                    "status": "active",
                })

        result = await _run_agent_async(
            cfg, thread_id, req.message,
            inputs={"messages": [("user", req.message)]},
            config=config,
        )

        if result.get("__interrupt__"):
            return JSONResponse(status_code=202, content={
                "status": "paused",
                "thread_id": thread_id,
                "interrupts": result.get("__interrupt__", []),
            })

        return {
            "status": result.get("status", "done"),
            "thread_id": thread_id,
            "reply": result.get("reply", ""),
            "agent_steps": result.get("agent_steps", []),
        }

    # ── /resume ─────────────────────────────────────────────────────────────

    @app.post("/resume")
    async def resume(req: ResumeRequest):
        """Resume a paused (human-in-the-loop) thread."""
        cfg = resolve_assistant_config()
        agent = build_assistant(cfg=cfg, checkpointer=_CHECKPOINTER)
        config = {"configurable": {"thread_id": req.thread_id}, "recursion_limit": 400}

        evt.get_or_create_queue(req.thread_id)

        loop = asyncio.get_event_loop()

        def _resume():
            result = agent.invoke(
                Command(resume={"decisions": req.decisions}), config=config
            )
            interrupts = result.get("__interrupt__") or result.get("__interrupts__")
            if interrupts:
                value = getattr(interrupts[0], "value", interrupts[0])
                evt.emit_paused(req.thread_id, [value])
                return JSONResponse(status_code=202, content={
                    "status": "paused",
                    "thread_id": req.thread_id,
                    "interrupts": [value],
                })
            messages = result.get("messages", [])
            reply = messages[-1].content if messages else ""
            agent_steps = _collect_agent_steps(result, req.thread_id)
            evt.emit_done(req.thread_id, reply, agent_steps)
            if _HAS_DB:
                _db.save_thread(req.thread_id, {
                    "thread_id": req.thread_id,
                    "status": "done",
                    "reply": reply,
                    "resumed": True,
                })
            return {
                "status": "done",
                "thread_id": req.thread_id,
                "reply": reply,
                "agent_steps": agent_steps,
            }

        return await loop.run_in_executor(_EXECUTOR, _resume)

    # ── /stream ─────────────────────────────────────────────────────────────

    @app.get("/stream")
    async def stream(thread_id: str = Query(...)):
        """
        SSE stream of agent step events for a given thread_id.
        Connect before or immediately after calling /run.

        Event types: agent_step | paused | done | error
        """
        # Ensure the queue exists (client may connect before /run)
        evt.get_or_create_queue(thread_id)

        return StreamingResponse(
            evt.event_stream(thread_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ── /history/{thread_id} ────────────────────────────────────────────────

    @app.get("/history/{thread_id}")
    async def history(thread_id: str):
        """Return thread metadata + agent steps from ChromaDB."""
        if not _HAS_DB:
            raise HTTPException(status_code=503, detail="Database not available")
        thread = _db.get_thread(thread_id)
        steps = _db.get_agent_steps(thread_id)
        return {
            "thread_id": thread_id,
            "metadata": thread or {},
            "agent_steps": steps,
        }

    # ── /threads ─────────────────────────────────────────────────────────────

    @app.get("/threads")
    async def threads(limit: int = Query(50, ge=1, le=200)):
        """List recent threads."""
        if not _HAS_DB:
            return {"threads": []}
        return {"threads": _db.list_threads(limit=limit)}

    # ── /projects ─────────────────────────────────────────────────────────────

    @app.get("/projects")
    async def projects(limit: int = Query(50, ge=1, le=200)):
        """List all known projects."""
        if not _HAS_DB:
            return {"projects": []}
        return {"projects": _db.list_projects(limit=limit)}

    # ── /search ──────────────────────────────────────────────────────────────

    @app.get("/search")
    async def search(
        q: str = Query(..., description="Natural-language search query"),
        thread_id: str | None = Query(None),
        n: int = Query(5, ge=1, le=20),
    ):
        """Semantic search over generated code using ChromaDB embeddings."""
        if not _HAS_DB:
            raise HTTPException(status_code=503, detail="Database not available")
        hits = _db.search_code(q, thread_id=thread_id, n_results=n)
        return {"results": hits}

    # ── /health ──────────────────────────────────────────────────────────────

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "db": "chromadb" if _HAS_DB else "unavailable",
        }

    return app


app = create_app()


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="AI Software Delivery Assistant — HTTP server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--project-path", help="Default project root")
    parser.add_argument("--reload", action="store_true", help="Enable hot-reload (dev)")
    args = parser.parse_args()

    if args.project_path:
        import os
        os.environ["ASSISTANT_PROJECT_PATH"] = args.project_path

    uvicorn.run(
        "assistant.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
