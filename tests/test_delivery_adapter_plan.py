"""Integration tests for the delivery sub-agent's plan-review pause/resume.

These exercise ``build_delivery_subagent`` end-to-end across the sub-agent
boundary (mirroring how deepagents' ``task`` tool invokes it inside a parent
graph that shares a checkpointer), using a *fake* delivery graph so no LLM is
required. The point is to prove that a ``plan_review`` interrupt raised deep
inside the delivery pipeline is surfaced to the top-level assistant and that
approve / reject decisions are forwarded back into the delivery run.
"""

from __future__ import annotations

import operator
import tempfile
import uuid
from types import SimpleNamespace
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import Command, interrupt

import assistant.delivery_adapter as da


class _FakeState(TypedDict, total=False):
    requirement: str
    plan_mode: bool
    plan_reviews_completed: Annotated[int, operator.add]
    approved: bool
    human_feedback: str
    delivery_package: str
    generated_code: dict
    completed_modules: list


def _make_fake_delivery_app():
    """A tiny checkpointed graph that pauses once (or repeatedly on reject) at a
    ``plan_review`` interrupt, then 'builds'."""

    b = StateGraph(_FakeState)

    def plan_review(state: _FakeState):
        if not state.get("plan_mode"):
            return {"approved": True}
        decision = interrupt(
            {"type": "plan_review", "prompt": "Approve this plan? ", "plan": "PLAN TEXT"}
        )
        if isinstance(decision, dict):
            choice = str(decision.get("choice", "")).strip().lower()
            feedback = decision.get("feedback", "") or ""
        else:
            choice, feedback = str(decision).strip().lower(), ""
        if choice == "no":
            return {"plan_reviews_completed": 1, "approved": False, "human_feedback": feedback}
        return {"plan_reviews_completed": 1, "approved": True}

    def build(state: _FakeState):
        return {
            "delivery_package": "BUILT PACKAGE",
            "generated_code": {"main.py": "print('hi')"},
            "completed_modules": ["core"],
        }

    b.add_node("plan_review", plan_review)
    b.add_node("build", build)
    b.add_edge(START, "plan_review")
    b.add_conditional_edges(
        "plan_review",
        lambda s: "build" if s.get("approved") else "plan_review",
        {"build": "build", "plan_review": "plan_review"},
    )
    b.add_edge("build", END)
    return b.compile(checkpointer=MemorySaver())


def _fake_cfg(plan_mode: bool):
    return SimpleNamespace(
        project_path=tempfile.mkdtemp(),
        tech_stack="Python/FastAPI",
        execution_mode="parallel",
        sandbox_enabled=False,
        plan_mode=plan_mode,
        delivery_provider="ollama",
        delivery_model="fake",
        delivery_base_url="http://localhost",
        delivery_ctx_size=None,
    )


def _fake_initial(wf):
    return {
        "requirement": wf.requirement,
        "plan_mode": wf.plan_mode,
        "plan_reviews_completed": 0,
        "approved": False,
        "human_feedback": "",
        "delivery_package": "",
        "generated_code": {},
        "completed_modules": [],
    }


def _build_parent(monkeypatch, plan_mode: bool):
    """Wrap the delivery sub-agent in a parent graph that shares a checkpointer,
    mirroring the deepagents ``task`` tool boundary."""
    monkeypatch.setattr(da, "app", _make_fake_delivery_app())
    monkeypatch.setattr(da, "config_to_initial_state", _fake_initial)

    subagent = da.build_delivery_subagent(_fake_cfg(plan_mode))
    runnable = subagent["runnable"]

    parent = StateGraph(MessagesState)

    def call_sub(state: MessagesState, config):
        res = runnable.invoke({"messages": state["messages"]}, config)
        return {"messages": res["messages"]}

    parent.add_node("call_sub", call_sub)
    parent.add_edge(START, "call_sub")
    parent.add_edge("call_sub", END)
    return parent.compile(checkpointer=MemorySaver())


def _last_reply(result):
    msgs = result.get("messages", [])
    return msgs[-1].content if msgs else ""


def _interrupt_value(result):
    ints = result.get("__interrupt__") or result.get("__interrupts__") or []
    if not ints:
        return None
    return getattr(ints[0], "value", ints[0])


def test_plan_review_pauses_and_approves(monkeypatch):
    parent = _build_parent(monkeypatch, plan_mode=True)
    cfg = {"configurable": {"thread_id": f"t-{uuid.uuid4().hex[:6]}"}, "recursion_limit": 100}

    result = parent.invoke({"messages": [("user", "build a login API")]}, config=cfg)
    value = _interrupt_value(result)
    assert value is not None, "expected the delivery plan_review to surface to the parent"
    assert value.get("type") == "plan_review"
    assert "PLAN TEXT" in value.get("plan", "")

    result = parent.invoke(
        Command(resume={"decisions": [{"choice": "yes", "feedback": ""}]}), config=cfg
    )
    assert _interrupt_value(result) is None, "should complete after approval"
    assert "BUILT PACKAGE" in _last_reply(result)


def test_plan_review_reject_then_approve(monkeypatch):
    parent = _build_parent(monkeypatch, plan_mode=True)
    cfg = {"configurable": {"thread_id": f"t-{uuid.uuid4().hex[:6]}"}, "recursion_limit": 100}

    result = parent.invoke({"messages": [("user", "build a login API")]}, config=cfg)
    assert _interrupt_value(result)["type"] == "plan_review"

    # Reject -> the delivery graph loops back and pauses again.
    result = parent.invoke(
        Command(resume={"decisions": [{"choice": "no", "feedback": "make it smaller"}]}),
        config=cfg,
    )
    value = _interrupt_value(result)
    assert value is not None and value["type"] == "plan_review", "reject should re-pause"

    # Approve the second time -> completes and builds.
    result = parent.invoke(
        Command(resume={"decisions": [{"choice": "yes", "feedback": ""}]}), config=cfg
    )
    assert _interrupt_value(result) is None
    assert "BUILT PACKAGE" in _last_reply(result)


def test_no_plan_mode_runs_unattended(monkeypatch):
    parent = _build_parent(monkeypatch, plan_mode=False)
    cfg = {"configurable": {"thread_id": f"t-{uuid.uuid4().hex[:6]}"}, "recursion_limit": 100}

    result = parent.invoke({"messages": [("user", "build a login API")]}, config=cfg)
    assert _interrupt_value(result) is None, "no plan mode should not pause"
    assert "BUILT PACKAGE" in _last_reply(result)
