"""
DevSwarm CLI – Shell
Main interactive loop for the terminal chatbot.
Handles user input, routes to the LangGraph orchestration graph,
renders agent outputs, and manages HITL approval prompts.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import Command
from rich.prompt import Prompt
from rich.console import Console

from devswarm.config import settings
from devswarm.agents.base import token_tracker
from devswarm.graph.state import DevSwarmState
from devswarm.cli.renderer import (
    console,
    render_banner,
    render_mode_badge,
    render_token_usage,
    render_plan,
    render_approval_card,
    render_agent_message,
    render_audit_log,
    print_info,
    print_success,
    print_error,
    print_warning,
    print_rule,
)

# ── Slash commands ─────────────────────────────────────────────────────────────

COMMANDS: dict[str, str] = {
    "/help": "Show available commands",
    "/plan": "Show the current implementation plan",
    "/audit": "Show the full audit log",
    "/usage": "Show token usage and context window info",
    "/workspace": "Show the session workspace path and list files",
    "/mode": "Show the current operating mode",
    "/session": "Show the current session ID",
    "/reset": "Start a new session (new workspace, fresh state)",
    "/exit": "Exit DevSwarm",
    "/quit": "Exit DevSwarm",
}

HELP_TEXT = "\n".join(
    f"  [bold cyan]{cmd}[/bold cyan] — {desc}"
    for cmd, desc in COMMANDS.items()
)


def _handle_command(cmd: str, state: DevSwarmState) -> bool:
    """
    Handle a slash command. Returns True if the command was handled (skip LLM call).
    """
    cmd = cmd.strip().lower()

    if cmd in ("/exit", "/quit"):
        print_success("Goodbye! DevSwarm session ended.")
        sys.exit(0)

    elif cmd == "/help":
        console.print(f"\n[bold]Available commands:[/bold]\n{HELP_TEXT}\n")

    elif cmd == "/plan":
        plan = state.get("plan") or []
        if plan:
            render_plan(plan)
        else:
            print_info("No plan yet. Describe a task to get started.")

    elif cmd == "/audit":
        render_audit_log(state.get("audit_log") or [])

    elif cmd == "/mode":
        mode = state.get("mode", "idle")
        print_info(f"Current mode: [bold]{mode.upper()}[/bold]")

    elif cmd == "/session":
        print_info(f"Session ID: {state.get('session_id', 'N/A')}")

    elif cmd == "/usage":
        render_token_usage(
            _session_token_usage.get("prompt_tokens", 0),
            _session_token_usage.get("completion_tokens", 0),
            settings.ollama_num_ctx,
        )

    elif cmd == "/workspace":
        ws = state.get("workspace_path", "N/A")
        print_info(f"Workspace: {ws}")
        from devswarm.tools.file_tools import list_files
        if ws != "N/A":
            files = list_files.invoke({"workspace": ws})
            console.print(f"[dim]{files}[/dim]")

    elif cmd == "/reset":
        print_warning("Use Ctrl+C and restart to begin a new session.")

    else:
        print_warning(f"Unknown command: {cmd!r}. Type [bold cyan]/help[/bold cyan] for available commands.")

    return True


# ── Session-level token usage (kept out of graph state) ──────────────────────

_session_token_usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0}


# ── Graph runner ───────────────────────────────────────────────────────────────

def _run_graph_step(
    graph,
    config: dict,
    state_input: dict | None,
    resume_value: str | None = None,
    prev_msg_count: int = 0,
) -> tuple[DevSwarmState | None, int]:
    """
    Run the graph, streaming events incrementally.
    Renders new AI messages as they arrive from each event.
    Returns (final_state, updated_message_count).
    """
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
            _render_new_messages(event, prev_msg_count)
            prev_msg_count = len(event.get("messages") or [])

        return last_state, prev_msg_count
    except Exception as e:
        print_error(f"Graph error: {e}")
        return None, prev_msg_count


def _render_new_messages(state: DevSwarmState, prev_msg_count: int) -> None:
    """Render any new AI messages added since prev_msg_count."""
    messages = state.get("messages") or []
    new_messages = messages[prev_msg_count:]
    for msg in new_messages:
        if isinstance(msg, AIMessage):
            render_agent_message(str(msg.content))


# ── Session initialisation ────────────────────────────────────────────────────

def _init_session() -> tuple[str, str, DevSwarmState]:
    """Create a new session: generate ID, create workspace, build initial state."""
    session_id = str(uuid.uuid4())
    workspace = settings.workspace_for(session_id)

    initial_state = DevSwarmState(
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
    return session_id, str(workspace), initial_state


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    # ── Startup ──────────────────────────────────────────────────────────────
    render_banner()
    print_info(f"Model: [bold]{settings.ollama_model}[/bold]  Base URL: {settings.ollama_base_url}")
    print_info("Type a task description to start, or [bold cyan]/help[/bold cyan] for commands.\n")

    # ── Lazy import graph (after settings loaded) ─────────────────────────────
    from devswarm.graph.builder import compiled_graph as graph

    # ── Session ───────────────────────────────────────────────────────────────
    session_id, workspace_path, current_state = _init_session()
    config = {"configurable": {"thread_id": session_id}}

    print_success(f"Session started  ·  workspace: {workspace_path}\n")
    print_rule()

    # ── Input loop ────────────────────────────────────────────────────────────
    while True:
        try:
            # Show mode badge + prompt
            render_mode_badge(current_state.get("mode", "idle"), session_id)
            user_input = Prompt.ask("[bold white]You[/bold white]").strip()
        except (KeyboardInterrupt, EOFError):
            print_success("\nGoodbye!")
            break

        if not user_input:
            continue

        # Slash commands
        if user_input.startswith("/"):
            _handle_command(user_input, current_state)
            continue

        prev_msg_count = len(current_state.get("messages") or [])

        # ── Check if graph is at any interrupt checkpoint ─────────────────────
        graph_state = graph.get_state(config)
        is_interrupted = graph_state is not None and bool(graph_state.next)

        if is_interrupted:
            # Resume graph with human's approval/decision
            print_info("Resuming from HITL checkpoint...")
            new_state, prev_msg_count = _run_graph_step(
                graph, config, None, resume_value=user_input,
                prev_msg_count=prev_msg_count,
            )
        else:
            state_input = {
                **current_state,
                "messages": (current_state.get("messages") or []) + [HumanMessage(content=user_input)],
            }
            new_state, prev_msg_count = _run_graph_step(
                graph, config, state_input,
                prev_msg_count=prev_msg_count,
            )

        if new_state is None:
            print_error("Graph returned no state. Try again.")
            continue

        # ── Update token usage from tracker ───────────────────────────────────
        current_state = new_state
        _session_token_usage.update(token_tracker.snapshot())

        # ── Show plan if just produced ────────────────────────────────────────
        plan = current_state.get("plan")
        if plan:
            render_plan(plan)

        # ── HITL prompt ───────────────────────────────────────────────────────
        hitl = current_state.get("hitl_pending")
        if hitl:
            render_approval_card(hitl)

        # ── Show token usage bar ──────────────────────────────────────────────
        render_token_usage(
            _session_token_usage.get("prompt_tokens", 0),
            _session_token_usage.get("completion_tokens", 0),
            settings.ollama_num_ctx,
        )

        print_rule()


if __name__ == "__main__":
    main()
