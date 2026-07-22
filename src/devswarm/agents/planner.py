"""
DevSwarm – Planner Agent
Produces a structured JSON task breakdown from user requirements.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser

from devswarm.agents.base import PLANNER_SYSTEM, make_llm
from devswarm.graph.state import PlanTask


def _extract_json(text: str) -> list[dict]:
    """
    Robustly extract a JSON array from LLM output, even if wrapped in markdown.
    """
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to extract from ```json ... ``` fences
    match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Find first [ ... ] block
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return []


def run_planner(user_request: str, context: str = "") -> list[PlanTask]:
    """
    Call the Planner LLM and return a list of PlanTask objects.

    Args:
        user_request: The raw user feature/bug/task description.
        context: Optional additional context (existing files, constraints).

    Returns:
        List of PlanTask dicts.
    """
    llm = make_llm(temperature=0.1)

    messages = [
        SystemMessage(content=PLANNER_SYSTEM),
        HumanMessage(
            content=(
                f"User request:\n{user_request}\n\n"
                + (f"Context:\n{context}\n\n" if context else "")
                + "Produce a structured implementation plan as a JSON array."
            )
        ),
    ]

    raw = llm.invoke(messages).content
    raw_tasks = _extract_json(raw)

    # Normalise and validate each task
    tasks: list[PlanTask] = []
    for i, t in enumerate(raw_tasks):
        tasks.append(
            PlanTask(
                id=t.get("id") or f"task-{i+1}",
                title=t.get("title", f"Task {i+1}"),
                description=t.get("description", ""),
                acceptance_criteria=t.get("acceptance_criteria", []),
                complexity=t.get("complexity", "medium"),
                status="todo",
                agent=t.get("agent", "coder"),
            )
        )

    return tasks
