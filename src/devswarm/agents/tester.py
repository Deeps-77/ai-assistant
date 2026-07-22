"""
DevSwarm – Tester Agent
Writes and runs tests for code in the session workspace.
Uses langgraph.prebuilt.create_react_agent for tool-calling.
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from devswarm.agents.base import TESTER_SYSTEM, make_llm
from devswarm.graph.state import PlanTask
from devswarm.tools.file_tools import FILE_TOOLS
from devswarm.tools.shell_tools import SHELL_TOOLS

TESTER_TOOLS = FILE_TOOLS + SHELL_TOOLS


def _extract_json_obj(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {
        "verdict": "fail",
        "summary": text,
        "tests_written": [],
        "tests_run": 0,
        "tests_passed": 0,
        "tests_failed": 0,
        "failures": [],
        "coverage_summary": "",
    }


def run_tester(task: PlanTask, workspace: str, context: str = "") -> dict:
    """
    Run the Tester agent to write and execute tests for a task.

    Args:
        task: The PlanTask just implemented and reviewed.
        workspace: Absolute path to the session workspace.
        context: Additional context.

    Returns:
        dict with keys: verdict, tests_written, tests_run, tests_passed,
                        tests_failed, failures, coverage_summary
    """
    llm = make_llm(temperature=0.05)
    agent = create_react_agent(llm, TESTER_TOOLS, prompt=TESTER_SYSTEM)

    prompt_text = (
        f"Workspace: {workspace}\n\n"
        f"Task ID: {task['id']}\n"
        f"Title: {task['title']}\n"
        f"Description: {task['description']}\n"
        f"Acceptance Criteria:\n"
        + "\n".join(f"  - {c}" for c in task["acceptance_criteria"])
        + (f"\n\nContext:\n{context}" if context else "")
        + "\n\n"
        "Steps:\n"
        "1. Read the workspace files to understand what was implemented.\n"
        "2. Write pytest tests for the new/changed code (save to tests/ directory).\n"
        "3. Run the tests using the run_tests tool.\n"
        "4. Return a final JSON test report matching the required schema."
    )

    try:
        result = agent.invoke(
            {"messages": [HumanMessage(content=prompt_text)]},
            {"recursion_limit": 25},
        )
        messages = result.get("messages", [])
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

        parsed = _extract_json_obj(final_answer)
        parsed["tool_calls"] = tool_calls
        return parsed
    except Exception as e:
        return {
            "verdict": "fail",
            "tests_written": [],
            "tests_run": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "failures": [{"test": "tester_agent", "error": str(e)}],
            "coverage_summary": "",
            "tool_calls": [],
        }
