"""Server-Sent Events (SSE) event emitter for the delivery assistant.

Each run has its own EventQueue identified by thread_id. The `/stream`
endpoint reads from that queue and pushes events to connected clients.

Design: asyncio.Queue per thread_id, with a global registry.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncIterator

# Global registry: thread_id -> Queue of SSE event dicts
_queues: dict[str, asyncio.Queue] = {}

# Sentinel to signal stream end
_DONE = object()


def get_or_create_queue(thread_id: str) -> asyncio.Queue:
    if thread_id not in _queues:
        _queues[thread_id] = asyncio.Queue()
    return _queues[thread_id]


def remove_queue(thread_id: str) -> None:
    _queues.pop(thread_id, None)


# ─── Emit helpers (called from sync code via run_coroutine_threadsafe) ────────


def emit_agent_step(
    thread_id: str,
    agent: str,
    status: str,       # "running" | "done" | "error"
    message: str,
    extra: dict | None = None,
) -> None:
    """Emit an agent step event to the SSE queue (thread-safe)."""
    event = {
        "type": "agent_step",
        "agent": agent,
        "status": status,
        "message": message,
        "timestamp": time.time(),
        **(extra or {}),
    }
    _put_nowait(thread_id, event)


def emit_done(thread_id: str, reply: str, agent_steps: list | None = None) -> None:
    """Emit the final 'done' event."""
    event = {
        "type": "done",
        "reply": reply,
        "agent_steps": agent_steps or [],
        "timestamp": time.time(),
    }
    _put_nowait(thread_id, event)
    _put_nowait(thread_id, _DONE)  # type: ignore[arg-type]


def emit_error(thread_id: str, message: str) -> None:
    """Emit an error event and close the stream."""
    event = {"type": "error", "message": message, "timestamp": time.time()}
    _put_nowait(thread_id, event)
    _put_nowait(thread_id, _DONE)  # type: ignore[arg-type]


def emit_paused(thread_id: str, interrupts: list) -> None:
    """Emit a 'paused' event (human-in-the-loop plan review required)."""
    event = {
        "type": "paused",
        "thread_id": thread_id,
        "interrupts": interrupts,
        "timestamp": time.time(),
    }
    _put_nowait(thread_id, event)
    _put_nowait(thread_id, _DONE)  # type: ignore[arg-type]


def _put_nowait(thread_id: str, item) -> None:
    """Put an item into the queue. Creates the queue if missing."""
    q = _queues.get(thread_id)
    if q is None:
        return
    try:
        q.put_nowait(item)
    except asyncio.QueueFull:
        pass


# ─── SSE async generator ─────────────────────────────────────────────────────


async def event_stream(thread_id: str, timeout: float = 300.0) -> AsyncIterator[str]:
    """Async generator that yields SSE-formatted strings for a given thread."""
    q = get_or_create_queue(thread_id)
    deadline = asyncio.get_event_loop().time() + timeout
    try:
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                yield _sse("error", {"message": "stream timeout"})
                break
            try:
                item = await asyncio.wait_for(q.get(), timeout=min(30.0, remaining))
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
                continue

            if item is _DONE:
                break

            event_type = item.get("type", "event") if isinstance(item, dict) else "event"
            yield _sse(event_type, item)
    finally:
        remove_queue(thread_id)


def _sse(event_type: str, data: dict) -> str:
    payload = json.dumps(data)
    return f"event: {event_type}\ndata: {payload}\n\n"
