
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import Command

from devswarm.config import settings
from devswarm.graph.state import DevSwarmState
from devswarm.agents.base import token_tracker


def _init_state(session_id: str | None = None) -> tuple[str, str, DevSwarmState]:
    session_id = session_id or str(uuid.uuid4())
    workspace = settings.workspace_for(session_id)
    initial = DevSwarmState(
        messages=[],
        mode="idle",
        session_id=session_id,
        workspace_path=str(workspace),
        plan=None,
        current_task_index=0,
        workspace_files={},
        hitl_pending=None,
        next_agent=None,
        audit_log=[],
        error=None,
        tool_calls_used=0,
        review_attempts=0,
    )
    return session_id, str(workspace), initial


def _run_in_thread(
    graph,
    config: dict,
    state_input: dict | None,
    resume_value: str | None = None,
    prev_msg_count: int = 0,
) -> tuple[dict[str, Any] | None, int, dict[str, Any] | None, list[dict] | None, dict | None]:
    try:
        if resume_value is not None:
            stream = graph.stream(
                Command(resume=resume_value),
                config=config,
                stream_mode="values",
            )
        else:
            stream = graph.stream(
                state_input,
                config=config,
                stream_mode="values",
            )

        last_state = None
        for event in stream:
            last_state = event
            prev_msg_count = len(event.get("messages") or [])

        return last_state, prev_msg_count, None, None, None
    except StopIteration:
        return None, prev_msg_count, None, None, None
    except Exception as e:
        return None, prev_msg_count, str(e), None, None
