"""
DevSwarm – LangGraph Node Functions
Each function is a node in the StateGraph.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.types import interrupt

from devswarm.config import settings
from devswarm.graph.state import AuditEntry, DevSwarmState, HITLRequest, PlanTask


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _append_audit(state: DevSwarmState, agent: str, action: str,
                  inputs: dict, outputs: dict) -> list[AuditEntry]:
    existing = list(state.get("audit_log") or [])
    existing.append(AuditEntry(
        timestamp=_now(),
        agent=agent,
        action=action,
        inputs=inputs,
        outputs=outputs,
    ))
    return existing


# ── Orchestrator node ─────────────────────────────────────────────────────────

def orchestrator_node(state: DevSwarmState) -> dict[str, Any]:
    from devswarm.agents.orchestrator import run_orchestrator
    return run_orchestrator(state)


# ── Planner node ──────────────────────────────────────────────────────────────

def planner_node(state: DevSwarmState) -> dict[str, Any]:
    from devswarm.agents.planner import run_planner

    # Extract the user's request from messages
    user_request = ""
    for msg in reversed(state.get("messages", [])):
        from langchain_core.messages import HumanMessage
        if isinstance(msg, HumanMessage):
            user_request = str(msg.content)
            break

    tasks = run_planner(user_request)

    audit = _append_audit(
        state, "planner", "produce_plan",
        {"user_request": user_request},
        {"tasks": [t["title"] for t in tasks]},
    )

    # Format plan summary for the user
    plan_md_lines = ["[Planner] Here is the implementation plan:\n"]
    for i, t in enumerate(tasks, 1):
        plan_md_lines.append(
            f"**{i}. {t['title']}** (`{t['complexity']}` complexity)\n"
            f"   {t['description']}\n"
            f"   _Criteria_: {'; '.join(t['acceptance_criteria'])}\n"
        )
    plan_md_lines.append(
        "\nType **approve** to start building, **reject** to cancel, "
        "or describe changes to adjust the plan."
    )

    return {
        "plan": tasks,
        "current_task_index": 0,
        "mode": "plan",
        "next_agent": "hitl",
        "hitl_pending": HITLRequest(
            checkpoint="after_plan",
            action_summary="Review and approve the implementation plan",
            context={"plan": [dict(t) for t in tasks]},
            options=["approve", "reject", "edit"],
        ),
        "audit_log": audit,
        "messages": [AIMessage(content="\n".join(plan_md_lines))],
    }


# ── HITL node ─────────────────────────────────────────────────────────────────

def hitl_node(state: DevSwarmState) -> dict[str, Any]:
    """
    Pause execution and wait for human approval via LangGraph interrupt().
    The CLI shell will resume the graph with the user's response.
    Handles plan approval (after_plan checkpoint).
    """
    pending = state.get("hitl_pending")
    if not pending:
        return {"hitl_pending": None}

    # This call suspends the graph and hands control back to the caller
    human_response: str = interrupt(pending)

    response_lower = human_response.strip().lower()

    if response_lower in ("approve", "yes", "y", "ok", "proceed", "go"):
        updates: dict[str, Any] = {
            "hitl_pending": None,
            "messages": [AIMessage(content="[HITL] ✅ Approved. Proceeding...")],
        }
        if pending["checkpoint"] == "after_plan":
            updates["mode"] = "build"
            updates["next_agent"] = "coder"
    elif response_lower in ("reject", "no", "n", "cancel", "stop", "abort"):
        updates = {
            "hitl_pending": None,
            "mode": "idle",
            "next_agent": "done",
            "messages": [AIMessage(content="[HITL] ❌ Rejected. Task cancelled.")],
        }
    else:
        # Treat as edit/redirect → re-plan
        updates = {
            "hitl_pending": None,
            "mode": "plan",
            "next_agent": "planner",
            "messages": [
                AIMessage(
                    content=f"[HITL] Redirecting with feedback: {human_response}"
                )
            ],
        }

    audit = _append_audit(
        state, "hitl", "approval_decision",
        {"checkpoint": pending["checkpoint"], "response": human_response},
        {"decision": response_lower},
    )
    updates["audit_log"] = audit
    return updates


# ── HITL after Coder node ─────────────────────────────────────────────────────

def hitl_after_coder_node(state: DevSwarmState) -> dict[str, Any]:
    """
    Pause after coder finishes, before reviewer runs.
    Lets the human review the code and approve/reject/redirect.
    """
    pending = state.get("hitl_pending")
    if not pending:
        return {"hitl_pending": None, "next_agent": "reviewer"}

    human_response: str = interrupt(pending)
    response_lower = human_response.strip().lower()

    if response_lower in ("approve", "yes", "y", "ok", "proceed", "go"):
        updates: dict[str, Any] = {
            "hitl_pending": None,
            "next_agent": "reviewer",
            "messages": [AIMessage(content="[HITL] ✅ Code approved. Starting review...")],
        }
    elif response_lower in ("reject", "no", "n", "cancel", "stop", "abort"):
        updates = {
            "hitl_pending": None,
            "mode": "idle",
            "next_agent": "done",
            "messages": [AIMessage(content="[HITL] ❌ Code rejected. Stopping.")],
        }
    else:
        updates = {
            "hitl_pending": None,
            "mode": "plan",
            "next_agent": "planner",
            "messages": [
                AIMessage(content=f"[HITL] Redirecting with feedback: {human_response}")
            ],
        }

    audit = _append_audit(
        state, "hitl", "code_approval",
        {"checkpoint": "after_coder", "response": human_response},
        {"decision": response_lower},
    )
    updates["audit_log"] = audit
    return updates


# ── HITL after Reviewer node ──────────────────────────────────────────────────

def hitl_after_reviewer_node(state: DevSwarmState) -> dict[str, Any]:
    """
    Pause after reviewer finishes, before tester runs.
    Lets the human approve the review and decide whether to run tests.
    """
    pending = state.get("hitl_pending")
    if not pending:
        return {"hitl_pending": None, "next_agent": "tester"}

    human_response: str = interrupt(pending)
    response_lower = human_response.strip().lower()

    if response_lower in ("approve", "yes", "y", "ok", "proceed", "go"):
        updates: dict[str, Any] = {
            "hitl_pending": None,
            "next_agent": "tester",
            "messages": [AIMessage(content="[HITL] ✅ Review approved. Starting tests...")],
        }
    elif response_lower in ("reject", "no", "n", "cancel", "stop", "abort"):
        updates = {
            "hitl_pending": None,
            "mode": "idle",
            "next_agent": "done",
            "messages": [AIMessage(content="[HITL] ❌ Review rejected. Stopping.")],
        }
    else:
        updates = {
            "hitl_pending": None,
            "mode": "plan",
            "next_agent": "planner",
            "messages": [
                AIMessage(content=f"[HITL] Redirecting with feedback: {human_response}")
            ],
        }

    audit = _append_audit(
        state, "hitl", "review_approval",
        {"checkpoint": "after_reviewer", "response": human_response},
        {"decision": response_lower},
    )
    updates["audit_log"] = audit
    return updates


# ── Coder node ────────────────────────────────────────────────────────────────

def coder_node(state: DevSwarmState) -> dict[str, Any]:
    from devswarm.agents.coder import run_coder

    plan = state.get("plan") or []
    idx = state.get("current_task_index", 0)
    if idx >= len(plan):
        return {"next_agent": "done"}

    task = plan[idx]
    workspace = state.get("workspace_path", "")

    # Mark in-progress
    updated_plan = list(plan)
    updated_plan[idx] = {**task, "status": "in_progress"}

    result = run_coder(task, workspace)

    msg_lines = [f"[Coder] Working on **{task['title']}**...\n"]
    if result.get("error"):
        msg_lines.append(f"⚠️ Error: {result['error']}")
        updated_plan[idx] = {**task, "status": "blocked"}
        next_a = "done"
    else:
        msg_lines.append(result.get("summary", ""))
        if result.get("tool_calls"):
            msg_lines.append(f"\n_Tools used: {len(result['tool_calls'])}_")
        updated_plan[idx] = {**task, "status": "review"}
        next_a = "hitl_after_coder"

    audit = _append_audit(
        state, "coder", "implement_task",
        {"task_id": task["id"]},
        {"summary": result.get("summary", ""), "error": result.get("error")},
    )

    hitl_pending = (
        HITLRequest(
            checkpoint="after_coder",
            action_summary=f"Review code for task: {task['title']}",
            context={"task_id": task["id"], "summary": result.get("summary", "")},
            options=["approve", "reject", "edit"],
        )
        if next_a == "hitl_after_coder"
        else None
    )

    return {
        "plan": updated_plan,
        "next_agent": next_a,
        "hitl_pending": hitl_pending,
        "audit_log": audit,
        "tool_calls_used": state.get("tool_calls_used", 0) + len(result.get("tool_calls", [])),
        "messages": [AIMessage(content="\n".join(msg_lines))],
    }


# ── Reviewer node ─────────────────────────────────────────────────────────────

def reviewer_node(state: DevSwarmState) -> dict[str, Any]:
    from devswarm.agents.reviewer import run_reviewer

    plan = state.get("plan") or []
    idx = state.get("current_task_index", 0)
    if idx >= len(plan):
        return {"next_agent": "done"}

    task = plan[idx]
    workspace = state.get("workspace_path", "")

    # Get coder summary from last AI message
    coder_summary = ""
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, AIMessage) and "[Coder]" in str(msg.content):
            coder_summary = str(msg.content)
            break

    result = run_reviewer(task, workspace, coder_summary)
    verdict = result.get("verdict", "needs_changes")

    updated_plan = list(plan)
    msg_lines = [f"[Reviewer] Review of **{task['title']}**\n"]
    msg_lines.append(f"Verdict: **{verdict.upper()}**")
    msg_lines.append(f"\n{result.get('summary', '')}")

    findings = result.get("findings", [])
    if findings:
        msg_lines.append("\n**Findings:**")
        for f in findings[:10]:
            icon = "🔴" if f.get("severity") == "error" else ("🟡" if f.get("severity") == "warning" else "🔵")
            msg_lines.append(
                f"{icon} [{f.get('severity','info').upper()}] {f.get('file', '')}:{f.get('line', '')} — {f.get('message', '')}"
            )

    if verdict == "approved":
        updated_plan[idx] = {**task, "status": "done"}
        next_a = "hitl_after_reviewer"
        current_attempts = 0  # reset on success
    elif verdict == "rejected":
        updated_plan[idx] = {**task, "status": "blocked"}
        next_a = "done"
        current_attempts = state.get("review_attempts", 0)
    else:
        current_attempts = state.get("review_attempts", 0) + 1
        if current_attempts >= settings.max_review_attempts:
            # Max retries exceeded → block instead of looping again
            updated_plan[idx] = {**task, "status": "blocked"}
            next_a = "done"
            msg_lines.append(
                f"\n_Max review attempts ({settings.max_review_attempts}) reached. Task blocked._"
            )
        else:
            # needs_changes → send back to coder (no HITL, loop directly)
            updated_plan[idx] = {**task, "status": "todo"}
            next_a = "coder"
            msg_lines.append("\n_Sending back to Coder for revisions..._")

    audit = _append_audit(
        state, "reviewer", "review_task",
        {"task_id": task["id"]},
        {"verdict": verdict, "findings_count": len(findings)},
    )

    hitl_pending = (
        HITLRequest(
            checkpoint="after_reviewer",
            action_summary=f"Proceed with tests for: {task['title']}",
            context={"task_id": task["id"], "verdict": verdict, "findings": findings[:5]},
            options=["approve", "reject", "edit"],
        )
        if next_a == "hitl_after_reviewer"
        else None
    )

    return {
        "plan": updated_plan,
        "next_agent": next_a,
        "hitl_pending": hitl_pending,
        "audit_log": audit,
        "messages": [AIMessage(content="\n".join(msg_lines))],
        "review_attempts": current_attempts,
    }


# ── Tester node ───────────────────────────────────────────────────────────────

def tester_node(state: DevSwarmState) -> dict[str, Any]:
    from devswarm.agents.tester import run_tester

    plan = state.get("plan") or []
    idx = state.get("current_task_index", 0)
    if idx >= len(plan):
        return {"next_agent": "done"}

    task = plan[idx]
    workspace = state.get("workspace_path", "")

    result = run_tester(task, workspace)
    verdict = result.get("verdict", "fail")

    msg_lines = [f"[Tester] Test results for **{task['title']}**\n"]
    msg_lines.append(
        f"Ran **{result.get('tests_run', 0)}** tests — "
        f"✅ {result.get('tests_passed', 0)} passed, "
        f"❌ {result.get('tests_failed', 0)} failed"
    )
    if result.get("coverage_summary"):
        msg_lines.append(f"Coverage: {result['coverage_summary']}")

    failures = result.get("failures", [])
    if failures:
        msg_lines.append("\n**Failed tests:**")
        for f in failures[:5]:
            msg_lines.append(f"  • `{f.get('test', '?')}`: {f.get('error', '?')}")

    # Advance to next task
    updated_plan = list(plan)
    if verdict == "pass":
        updated_plan[idx] = {**task, "status": "done"}
        msg_lines.append("\n✅ All tests pass — task complete.")
        next_idx = idx + 1
        next_a = "coder" if next_idx < len(plan) else "done"
    else:
        updated_plan[idx] = {**task, "status": "blocked"}
        msg_lines.append("\n❌ Tests failed — task blocked.")
        next_idx = idx
        next_a = "done"

    audit = _append_audit(
        state, "tester", "run_tests",
        {"task_id": task["id"]},
        {"verdict": verdict, "passed": result.get("tests_passed", 0), "failed": result.get("tests_failed", 0)},
    )

    return {
        "plan": updated_plan,
        "current_task_index": next_idx,
        "next_agent": next_a,
        "audit_log": audit,
        "tool_calls_used": state.get("tool_calls_used", 0) + len(result.get("tool_calls", [])),
        "messages": [AIMessage(content="\n".join(msg_lines))],
    }
