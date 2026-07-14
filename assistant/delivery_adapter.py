"""Bridge between the existing LangGraph delivery pipeline and deepagents.

The delivery pipeline in :mod:`graph` is a custom ``StateGraph`` driven by a
``SoftwareState`` dict, not the ``messages`` schema deepagents sub-agents
expect. This module wraps it behind a tiny ``MessagesState`` graph so it can be
registered as a ``CompiledSubAgent`` and invoked through the ``task`` tool.
"""

from __future__ import annotations

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import MessagesState, StateGraph, END
from langgraph.types import Command, interrupt

from deepagents.middleware.subagents import CompiledSubAgent

from agents import _parse_plan_decision
from config import WorkflowConfig, WorkflowMode
from main import config_to_initial_state
from graph import app

INTENTS: dict[str, list[str]] = {
    "analyze": [
        "analyze", "analyse", "review", "audit", "understand", "explore",
        "read the project", "what does this", "what is this", "summarise",
        "summarize", "tell me about", "explain", "describe", "walk me through",
        "how does", "how is this", "report on",
    ],
    "update": [
        "update", "add", "change", "modify", "extend", "refactor", "fix",
        "implement", "integrate", "improve", "enhance", "patch",
    ],
    "create_new": [
        "build", "create", "make", "generate", "new project", "scaffold",
        "start", "design", "develop",
    ],
}


def _last_human_text(messages: list) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            content = msg.content
            return content if isinstance(content, str) else str(content)
    if messages:
        content = messages[-1].content
        return content if isinstance(content, str) else str(content)
    return ""


def _repo_exists(path: str) -> bool:
    if not os.path.isdir(path):
        return False
    try:
        return any(os.scandir(path))
    except OSError:
        return False


def detect_mode(text: str, project_exists: bool) -> str:
    lowered = text.lower()
    for mode, keywords in INTENTS.items():
        if any(kw in lowered for kw in keywords):
            if mode == "analyze" and not project_exists:
                continue
            return mode
    return "update" if project_exists else "create_new"


def _summarize(result: dict[str, Any], mode: str) -> str:
    # Analyze mode is read-only: just surface the generated report.
    if mode == "analyze":
        report = result.get("delivery_package") or result.get("analysis_report") or ""
        if report:
            return report
        return "Analysis complete (no report content generated)."

    completed = result.get("completed_modules", []) or []
    written = result.get("written_files", {}) or {}
    tests = result.get("test_results", {}) or {}
    package = result.get("delivery_package") or ""

    lines = [f"Delivery complete (mode: {mode})."]
    lines.append(f"Modules completed: {len(completed)} -> {completed}")
    if written:
        ok = sum(1 for v in written.values() if v == "ok")
        errors = len(written) - ok
        lines.append(f"Files written: {ok} ok, {errors} errors ({len(written)} total)")
    if tests:
        passed = sum(1 for t in tests.values() if isinstance(t, dict) and t.get("success"))
        lines.append(f"Tests: {passed}/{len(tests)} modules passing")
    if package:
        lines.append("")
        lines.append("Delivery summary:")
        lines.append(package[:2000])
    return "\n".join(lines)


def _inner_thread_id(config: RunnableConfig | None) -> str:
    """Derive a delivery thread id that is stable across an outer plan-review
    pause/resume cycle yet unique per new delivery request.

    ``checkpoint_ns`` is deterministic across an interrupt/resume replay of the
    same task, and differs for a fresh task invocation, so it (combined with the
    outer ``thread_id``) uniquely and stably identifies one delivery run.
    """
    cfg = (config or {}).get("configurable", {}) if isinstance(config, dict) else {}
    seed = f"{cfg.get('thread_id', '')}|{cfg.get('checkpoint_ns', '')}"
    return "delivery-" + hashlib.sha1(seed.encode()).hexdigest()[:16]


def _isolated_invoke(*args, **kwargs):
    """Run the delivery graph in a fresh thread so it does NOT inherit the
    parent assistant's subgraph context.

    When ``app.invoke`` is called directly inside the delivery sub-agent node,
    langgraph treats the delivery graph as a subgraph and *propagates* its
    ``interrupt()`` straight to the top-level agent, bypassing this adapter's
    control. A new thread starts with clean contextvars, so the delivery graph
    manages its own interrupts (returning ``__interrupt__``), letting us decide
    which ones to surface (plan review) and which to auto-resolve.
    """
    with ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(lambda: app.invoke(*args, **kwargs)).result()


def _interrupts(result: Any) -> list:
    if isinstance(result, dict):
        return result.get("__interrupt__") or result.get("__interrupts__") or []
    return []


def _interrupt_value(item: Any) -> Any:
    return getattr(item, "value", item)


def _plan_review_value(result: Any) -> dict | None:
    for item in _interrupts(result):
        value = _interrupt_value(item)
        if isinstance(value, dict) and value.get("type") == "plan_review":
            return value
    return None


def build_delivery_subagent(cfg) -> CompiledSubAgent:
    """Return a ``CompiledSubAgent`` that runs the delivery pipeline end-to-end."""

    def run_delivery(state: MessagesState, config: RunnableConfig) -> dict:
        user_text = _last_human_text(state.get("messages", []))
        project_path = cfg.project_path
        project_exists = _repo_exists(project_path)

        mode = detect_mode(user_text, project_exists)
        wf = WorkflowConfig(
            mode=WorkflowMode(mode),
            requirement=user_text,
            project_path=project_path,
            tech_stack=cfg.tech_stack,
            output_dir=project_path,
            execution_mode=cfg.execution_mode,
            sandbox_enabled=cfg.sandbox_enabled,
            plan_mode=cfg.plan_mode,
            provider=cfg.delivery_provider,
            llm_model=cfg.delivery_model,
            llm_base_url=cfg.delivery_base_url,
            ctx_size=cfg.delivery_ctx_size,
            thread_id=_inner_thread_id(config),
        )

        initial = config_to_initial_state(wf)
        run_cfg = {
            "configurable": {"thread_id": wf.thread_id},
            "recursion_limit": wf.recursion_limit,
        }

        # Start the delivery graph only if this inner thread hasn't run yet.
        # On a re-execution (after an outer plan-review resume) the inner graph
        # is already checkpointed mid-run, so we continue it instead.
        snapshot = app.get_state(run_cfg)
        started = bool(snapshot.next) or bool(snapshot.values)
        if not started:
            result = _isolated_invoke(initial, config=run_cfg)
        else:
            result = dict(snapshot.values)
            result["__interrupt__"] = list(snapshot.interrupts or [])

        # Surface each pending inner-graph interrupt to the top-level human and
        # resume the inner graph with their decision. There is exactly one
        # pending interrupt per re-execution, so we always inject the human's
        # decision here. (The previous logic tried to skip "already applied"
        # gates via a counter that reset on every resume, which caused
        # reject-then-approve flows to skip the inject and hang.)
        while True:
            interrupts = _interrupts(result)
            if not interrupts:
                break
            # Surface the active interrupt to the top-level human. This pauses the whole
            # assistant; on resume the decision is returned here.
            value = _interrupt_value(interrupts[0])
            if not isinstance(value, dict):
                value = {"type": "unknown", "data": value}
            decision = interrupt(value)
            choice, feedback = _parse_plan_decision(decision)
            result = _isolated_invoke(
                Command(resume={"choice": choice, "feedback": feedback}),
                config=run_cfg,
            )

        return {"messages": [AIMessage(content=_summarize(result, mode))]}

    builder = StateGraph(MessagesState)
    builder.add_node("run_delivery", run_delivery)
    builder.set_entry_point("run_delivery")
    builder.add_edge("run_delivery", END)

    return CompiledSubAgent(
        name="software_delivery",
        description=(
            "End-to-end software delivery engine. Use it for substantial, "
            "multi-file work: build a new project from a requirement, analyze "
            "an existing codebase, or update/extend a project with new modules. "
            "It plans, codes modules in parallel, reviews, fixes, runs tests, "
            "and writes the result to the project directory."
        ),
        runnable=builder.compile(),
    )
