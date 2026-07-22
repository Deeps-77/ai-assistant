"""
DevSwarm – LangGraph Graph Builder
Assembles the StateGraph with all nodes, edges, and conditional routing.
"""

from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from devswarm.graph.state import DevSwarmState
from devswarm.graph.nodes import (
    orchestrator_node,
    planner_node,
    hitl_node,
    coder_node,
    reviewer_node,
    tester_node,
)
from devswarm.config import settings


def _route_from_orchestrator(
    state: DevSwarmState,
) -> Literal["planner", "coder", "reviewer", "tester", "hitl", "__end__"]:
    """Conditional edge: route based on orchestrator's next_agent decision."""
    next_a = state.get("next_agent", "done")
    if next_a == "done" or next_a is None:
        return END
    return next_a  # type: ignore[return-value]


def _route_from_hitl(
    state: DevSwarmState,
) -> Literal["planner", "coder", "__end__"]:
    """After HITL, route based on updated next_agent."""
    next_a = state.get("next_agent", "done")
    if next_a in ("coder",):
        return "coder"
    if next_a in ("planner",):
        return "planner"
    return END


def _route_from_coder(
    state: DevSwarmState,
) -> Literal["reviewer", "__end__"]:
    next_a = state.get("next_agent", "done")
    if next_a == "reviewer":
        return "reviewer"
    return END


def _route_from_reviewer(
    state: DevSwarmState,
) -> Literal["tester", "coder", "__end__"]:
    next_a = state.get("next_agent", "done")
    if next_a == "tester":
        return "tester"
    if next_a == "coder":
        return "coder"
    return END


def _route_from_tester(
    state: DevSwarmState,
) -> Literal["coder", "__end__"]:
    next_a = state.get("next_agent", "done")
    if next_a == "coder":
        return "coder"
    return END


def build_graph() -> StateGraph:
    """Build and compile the DevSwarm LangGraph StateGraph."""
    builder = StateGraph(DevSwarmState)

    # ── Add nodes ─────────────────────────────────────────────────────────────
    builder.add_node("orchestrator", orchestrator_node)
    builder.add_node("planner", planner_node)
    builder.add_node("hitl", hitl_node)
    builder.add_node("coder", coder_node)
    builder.add_node("reviewer", reviewer_node)
    builder.add_node("tester", tester_node)

    # ── Entry ─────────────────────────────────────────────────────────────────
    builder.add_edge(START, "orchestrator")

    # ── Conditional edges from orchestrator ───────────────────────────────────
    builder.add_conditional_edges(
        "orchestrator",
        _route_from_orchestrator,
        {
            "planner": "planner",
            "coder": "coder",
            "reviewer": "reviewer",
            "tester": "tester",
            "hitl": "hitl",
            END: END,
        },
    )

    # ── Planner always goes to hitl (plan approval required) ──────────────────
    builder.add_edge("planner", "hitl")

    # ── HITL conditional routing ───────────────────────────────────────────────
    builder.add_conditional_edges(
        "hitl",
        _route_from_hitl,
        {"planner": "planner", "coder": "coder", END: END},
    )

    # ── Coder → Reviewer ──────────────────────────────────────────────────────
    builder.add_conditional_edges(
        "coder",
        _route_from_coder,
        {"reviewer": "reviewer", END: END},
    )

    # ── Reviewer → Tester or back to Coder ────────────────────────────────────
    builder.add_conditional_edges(
        "reviewer",
        _route_from_reviewer,
        {"tester": "tester", "coder": "coder", END: END},
    )

    # ── Tester → next task Coder or done ──────────────────────────────────────
    builder.add_conditional_edges(
        "tester",
        _route_from_tester,
        {"coder": "coder", END: END},
    )

    return builder


# Singleton compiled graph (MemorySaver for M0)
_checkpointer = MemorySaver()

compiled_graph = build_graph().compile(
    checkpointer=_checkpointer,
    interrupt_before=["hitl"],
)
