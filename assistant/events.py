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

# Global registry: thread_id -> (Queue of SSE event dicts, owning event loop).
# The event loop is captured when the queue is created (in the async /stream
# handler) so that emit helpers running on a worker thread can safely schedule
# puts on the correct loop via loop.call_soon_threadsafe.
_queues: dict[str, tuple[asyncio.Queue, asyncio.AbstractEventLoop]] = {}

# Sentinel to signal stream end
_DONE = object()


def get_or_create_queue(thread_id: str) -> asyncio.Queue:
    if thread_id not in _queues:
        loop = asyncio.get_running_loop()
        _queues[thread_id] = (asyncio.Queue(), loop)
    return _queues[thread_id][0]


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
    """Put an item into the queue from any thread (thread-safe).

    Emit helpers are called from worker threads (e.g. via
    ``loop.run_in_executor``), so we must marshal the put onto the event loop
    that owns the queue instead of calling ``Queue.put_nowait`` directly.
    """
    entry = _queues.get(thread_id)
    if entry is None:
        return
    q, loop = entry
    try:
        loop.call_soon_threadsafe(q.put_nowait, item)
    except RuntimeError:
        # Loop is closed; drop the event.
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
