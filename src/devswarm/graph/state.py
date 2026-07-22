"""
DevSwarm Graph State – the single shared TypedDict passed between all nodes.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


# ── Plan task ────────────────────────────────────────────────────────────────

class PlanTask(TypedDict):
    id: str
    title: str
    description: str
    acceptance_criteria: list[str]
    complexity: Literal["low", "medium", "high"]
    status: Literal["todo", "in_progress", "review", "done", "blocked"]
    agent: Literal["planner", "coder", "reviewer", "tester", "tracker"]


# ── Audit entry ───────────────────────────────────────────────────────────────

class AuditEntry(TypedDict):
    timestamp: str
    agent: str
    action: str
    inputs: dict[str, Any]
    outputs: dict[str, Any]


# ── HITL interrupt payload ────────────────────────────────────────────────────

class HITLRequest(TypedDict):
    checkpoint: str          # e.g. "after_plan", "before_shell_exec"
    action_summary: str      # human-readable description of what needs approval
    context: dict[str, Any]  # supporting data (plan JSON, diff, command, etc.)
    options: list[str]       # ["approve", "reject", "edit"]


# ── Main state ────────────────────────────────────────────────────────────────

class DevSwarmState(TypedDict):
    # Chat messages (accumulated via add_messages reducer)
    messages: Annotated[list[BaseMessage], add_messages]

    # Operating mode
    mode: Literal["plan", "build", "idle"]

    # Session
    session_id: str
    workspace_path: str   # absolute path to this session's sandbox

    # Plan
    plan: list[PlanTask] | None
    current_task_index: int

    # File changes tracked by agents
    workspace_files: dict[str, str]   # relative_path -> content

    # HITL
    hitl_pending: HITLRequest | None

    # Routing: which node to execute next after orchestrator decides
    next_agent: Literal["planner", "coder", "reviewer", "tester", "hitl", "done"] | None

    # Audit log
    audit_log: list[AuditEntry]

    # Error tracking
    error: str | None

    # Tool call counter (budget)
    tool_calls_used: int
