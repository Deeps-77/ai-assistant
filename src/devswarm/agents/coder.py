"""
DevSwarm – Coder Agent
Implements code changes in the session workspace using file and shell tools.
Uses langgraph.prebuilt.create_react_agent for tool-calling.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from devswarm.agents.base import CODER_SYSTEM, make_llm
from devswarm.graph.state import PlanTask
from devswarm.tools.file_tools import FILE_TOOLS
from devswarm.tools.shell_tools import SHELL_TOOLS

CODER_TOOLS = FILE_TOOLS + SHELL_TOOLS


def run_coder(task: PlanTask, workspace: str, context: str = "") -> dict:
    """
    Execute the Coder agent for a single plan task.

    Args:
        task: The PlanTask to implement.
        workspace: Absolute path to the session workspace.
        context: Additional context (previous steps, constraints).

    Returns:
        dict with keys: summary, tool_calls, error
    """
    llm = make_llm(temperature=0.05)
    agent = create_react_agent(llm, CODER_TOOLS, prompt=CODER_SYSTEM)

    prompt_text = (
        f"Workspace: {workspace}\n\n"
        f"Task ID: {task['id']}\n"
        f"Title: {task['title']}\n"
        f"Description: {task['description']}\n"
        f"Acceptance Criteria:\n"
        + "\n".join(f"  - {c}" for c in task["acceptance_criteria"])
        + (f"\n\nAdditional context:\n{context}" if context else "")
        + "\n\nImplement this task now. Use the available tools to read/write files "
          "and run shell commands within the workspace. Report all changes made."
    )

    try:
        result = agent.invoke(
            {"messages": [HumanMessage(content=prompt_text)]},
            {"recursion_limit": 50},
        )
        messages = result.get("messages", [])
        # Extract tool calls from message history
        tool_calls = []
        final_answer = ""
        for msg in messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append({
                        "tool": tc.get("name", ""),
                        "input": tc.get("args", {}),
                        "output": "",
                    })
            if hasattr(msg, "content") and isinstance(msg.content, str) and msg.content:
                final_answer = msg.content

        return {
            "summary": final_answer,
            "tool_calls": tool_calls,
            "error": None,
        }
    except Exception as e:
        return {"summary": "", "tool_calls": [], "error": str(e)}
