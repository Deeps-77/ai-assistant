"""
DevSwarm – Orchestrator Agent
The supervisor node that interprets user intent and routes to sub-agents.
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from devswarm.agents.base import ORCHESTRATOR_SYSTEM, make_llm
from devswarm.graph.state import DevSwarmState


_ROUTE_PROMPT = """\
Given the conversation so far and the current state, decide what to do next.

Current mode: {mode}
Plan status: {plan_status}
Current task index: {task_index} / {total_tasks}
Last user message: {last_user_message}

Respond with a JSON object:
{{
  "reasoning": "brief explanation of your decision",
  "next_agent": "<one of: planner | coder | reviewer | tester | hitl | done>",
  "message_to_user": "what to tell the user right now (empty string if routing silently)"
}}

Rules:
- If mode is "plan" and there is no plan yet → next_agent = "planner"
- If mode is "plan" and there is an unapproved plan → next_agent = "hitl" (checkpoint: after_plan)
- If mode is "build" and current_task_index < total_tasks:
    - If current task status is "todo" or "in_progress" → next_agent = "coder"
    - If current task status is "review" → next_agent = "reviewer"
    - If current task status is "done" → next_agent = "tester" (if not yet tested)
- If all tasks are done → next_agent = "done"
- If the user just sent a redirect/clarification mid-build → next_agent = "planner" to replan
"""


def run_orchestrator(state: DevSwarmState) -> dict[str, Any]:
    """
    Supervisor node: decide routing and produce a user-facing message if needed.
    Returns a partial state update dict.
    """
    llm = make_llm(temperature=0.0)

    # Summarise plan status
    plan = state.get("plan") or []
    plan_status = "no plan" if not plan else (
        f"{sum(1 for t in plan if t['status'] == 'done')}/{len(plan)} tasks done"
    )
    last_user = ""
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            last_user = str(msg.content)[:500]
            break

    routing_prompt = _ROUTE_PROMPT.format(
        mode=state.get("mode", "plan"),
        plan_status=plan_status,
        task_index=state.get("current_task_index", 0),
        total_tasks=len(plan),
        last_user_message=last_user,
    )

    messages = [
        SystemMessage(content=ORCHESTRATOR_SYSTEM),
        HumanMessage(content=routing_prompt),
    ]

    raw = llm.invoke(messages).content

    # Parse routing decision
    def _extract(text: str) -> dict:
        try:
            return json.loads(text)
        except Exception:
            pass
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        return {"reasoning": "", "next_agent": "done", "message_to_user": text}

    decision = _extract(raw)
    next_agent = decision.get("next_agent", "done")
    msg_to_user = decision.get("message_to_user", "")

    updates: dict[str, Any] = {"next_agent": next_agent}
    if msg_to_user:
        updates["messages"] = [AIMessage(content=f"[Orchestrator] {msg_to_user}")]

    return updates
