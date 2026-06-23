from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from state import SoftwareState
from agents import (
    planner_node,
    architect_node,
    quality_gen_node,
    backend_lead_node,
    module_planner_node,
    module_coder_node,
    reviewer_node,
    fixer_node,
    complete_module_node,
    qa_node,
    delivery_node,
    project_init_node,
    file_writer_node,
    project_reader_node,
    project_analyzer_node,
)


def route_by_mode(state: SoftwareState) -> Literal["planner", "project_reader"]:
    mode = state.get("mode", "create_new")
    if mode in ("analyze", "update"):
        return "project_reader"
    return "planner"


def route_after_backend_lead(state: SoftwareState) -> Literal["module_planner", "qa"]:
    if state.get("current_module"):
        return "module_planner"
    return "qa"


def route_after_review(state: SoftwareState) -> Literal["fixer", "complete_module"]:
    threshold = state.get("review_threshold", 7)
    score = state.get("review_score", 0) or 0
    attempts = state.get("fix_attempts", 0)
    max_attempts = state.get("max_fix_attempts", 3)

    if score >= threshold:
        print(f"   Review PASSED (score={score}/{threshold}). Completing module.")
        return "complete_module"

    if attempts >= max_attempts:
        print(
            f"   Max fix attempts reached ({attempts}/{max_attempts}). "
            f"Force-completing module (score={score})."
        )
        return "complete_module"

    print(
        f"   Review FAILED (score={score}/{threshold}, "
        f"attempts={attempts}/{max_attempts}). Sending to fixer."
    )
    return "fixer"


workflow = StateGraph(SoftwareState)

workflow.add_node("planner", planner_node)
workflow.add_node("architect", architect_node)
workflow.add_node("quality_gen", quality_gen_node)
workflow.add_node("project_init", project_init_node)
workflow.add_node("backend_lead", backend_lead_node)
workflow.add_node("module_planner", module_planner_node)
workflow.add_node("module_coder", module_coder_node)
workflow.add_node("reviewer", reviewer_node)
workflow.add_node("fixer", fixer_node)
workflow.add_node("complete_module", complete_module_node)
workflow.add_node("qa", qa_node)
workflow.add_node("file_writer", file_writer_node)
workflow.add_node("delivery", delivery_node)
workflow.add_node("project_reader", project_reader_node)
workflow.add_node("project_analyzer", project_analyzer_node)

workflow.set_conditional_entry_point(
    route_by_mode,
    {
        "planner": "planner",
        "project_reader": "project_reader",
    },
)

workflow.add_edge("project_reader", "project_analyzer")
workflow.add_edge("project_analyzer", "planner")

workflow.add_edge("planner", "architect")
workflow.add_edge("architect", "quality_gen")
workflow.add_edge("quality_gen", "project_init")
workflow.add_edge("project_init", "backend_lead")

workflow.add_conditional_edges(
    "backend_lead",
    route_after_backend_lead,
    {
        "module_planner": "module_planner",
        "qa": "qa",
    },
)

workflow.add_edge("module_planner", "module_coder")
workflow.add_edge("module_coder", "reviewer")

workflow.add_conditional_edges(
    "reviewer",
    route_after_review,
    {
        "fixer": "fixer",
        "complete_module": "complete_module",
    },
)

workflow.add_edge("fixer", "reviewer")
workflow.add_edge("complete_module", "backend_lead")
workflow.add_edge("qa", "file_writer")
workflow.add_edge("file_writer", "delivery")
workflow.add_edge("delivery", END)


memory = MemorySaver()
app = workflow.compile(checkpointer=memory)
