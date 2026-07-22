"""
DevSwarm Tools – HITL (Human-in-the-Loop)
Provides a mechanism for agents to register approval requests,
which the CLI shell resolves interactively.
"""

from __future__ import annotations

from langchain_core.tools import tool


@tool
def request_approval(
    checkpoint: str,
    action_summary: str,
    context_json: str = "{}",
) -> str:
    """
    Signal that a HITL checkpoint has been reached and human approval is needed.

    This tool does NOT block execution by itself — it registers the request
    in the agent state. The LangGraph interrupt() mechanism, triggered by the
    graph node, is what actually pauses execution and hands control to the CLI.

    Args:
        checkpoint: Name of the checkpoint (e.g. "after_plan", "before_shell_exec").
        action_summary: Human-readable description of what needs approval.
        context_json: JSON string with supporting context (plan, diff, command, etc.).

    Returns:
        A sentinel string indicating the approval request was registered.
    """
    return f"[HITL_PENDING] checkpoint={checkpoint!r} | {action_summary}"


HITL_TOOLS = [request_approval]
