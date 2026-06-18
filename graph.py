# graph.py
from typing import Literal
from langgraph.graph import StateGraph, END
from state import SoftwareState
from agents import (
    planner_node, architect_node, backend_lead_node, 
    module_agent_node, reviewer_node, fixer_node
)

# --- Conditional Edges ---

def should_review_or_fix(state: SoftwareState) -> Literal["fixer", "backend_lead"]:
    """
    Router after Review.
    If score < 8, go to Fixer.
    Otherwise, go to Backend Lead to handle next module.
    """
    score = state.get("review_score", 0)
    print(f"Review Score: {score}/10")
    
    if score < 8:
        return "fixer"
    else:
        print("Review Passed. Marking module as complete.")
        # Note: We handle the 'completed' list logic inside the transition or next node
        # Here we just route back to the Lead to pick the next task
        return "backend_lead"

def check_modules_remaining(state: SoftwareState) -> Literal["module_agent", "qa_or_end"]:
    """
    Router at Backend Lead.
    If current_module is not None, we have work to do -> go to module_agent.
    If current_module is None, we are done -> go to QA (or END for now).
    """
    if state.get("current_module"):
        return "module_agent"
    else:
        return "qa_or_end"

# --- Graph Construction ---

workflow = StateGraph(SoftwareState)

# Add Nodes
workflow.add_node("planner", planner_node)
workflow.add_node("architect", architect_node)
workflow.add_node("backend_lead", backend_lead_node)
workflow.add_node("module_agent", module_agent_node)
workflow.add_node("reviewer", reviewer_node)
workflow.add_node("fixer", fixer_node)

# Add Edges (Linear Flow)
workflow.set_entry_point("planner")
workflow.add_edge("planner", "architect")
workflow.add_edge("architect", "backend_lead")

# Add Dynamic Routing
# After Backend Lead decides what to do
workflow.add_conditional_edges(
    "backend_lead",
    check_modules_remaining,
    {
        "module_agent": "module_agent",
        "qa_or_end": END # Phase 1 ends here. Phase 2 adds QA Agent.
    }
)

# After Coding, Review
workflow.add_edge("module_agent", "reviewer")

# After Review, decide Fix or Next Module
workflow.add_conditional_edges(
    "reviewer",
    should_review_or_fix,
    {
        "fixer": "fixer",
        "backend_lead": "backend_lead"
    }
)

# After Fixing, go back to Coding (or directly to Review? Let's go to Review)
# The prompt said: Fix -> Review.
workflow.add_edge("fixer", "reviewer")

# Compile
app = workflow.compile()