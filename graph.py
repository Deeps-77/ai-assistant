from typing import Literal
from langgraph.constants import Send
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from state import SoftwareState, WorkerState
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
    human_review_node,
    qa_node,
    delivery_node,
    project_init_node,
    file_writer_node,
    project_reader_node,
    project_analyzer_node,
    sandbox_setup_node,
    test_executor_node,
    test_fixer_node,
    sandbox_cleanup_node,
    _build_worker_payload,
    _build_sandbox_worker_payload,
    worker_module_planner,
    worker_coder,
    worker_reviewer,
    worker_fixer,
    worker_complete,
    sandbox_worker_node,
)


# Shared routing

def route_by_mode(state: SoftwareState) -> Literal["planner", "project_reader"]:
    mode = state.get("mode", "create_new")
    if mode in ("analyze", "update"):
        return "project_reader"
    return "planner"


def route_after_backend_lead(state: SoftwareState) -> Literal["module_planner", "human_review"]:
    if state.get("current_module"):
        return "module_planner"
    return "human_review"


def route_after_review(state: SoftwareState) -> Literal["fixer", "complete_module"]:
    threshold = state.get("review_threshold", 7)
    score = state.get("review_score", 0) or 0
    attempts = state.get("fix_attempts", 0)
    max_attempts = state.get("max_fix_attempts", 3)
    score_history = state.get("score_history", [])

    if score >= threshold:
        print(f"   Review PASSED (score={score}/{threshold}). Completing module.")
        return "complete_module"

    if attempts >= max_attempts:
        print(f"   Max fix attempts reached ({attempts}/{max_attempts}). "
              f"Force-completing module (score={score}).")
        return "complete_module"

    # Convergence detection: if score hasn't improved over last N reviews, break early
    if len(score_history) >= 4:
        # Compare best of last 2 vs best of 2 before that
        recent = max(score_history[-2:])
        prior = max(score_history[-4:-2])
        if recent <= prior:
            print(f"   No score improvement (recent: {score_history[-2:]}, prior: {score_history[-4:-2]}). "
                  f"Converged — force-completing module (score={score}).")
            return "complete_module"
    elif len(score_history) == 3:
        # If all 3 scores are identical and below threshold, converged
        if len(set(score_history)) == 1:
            print(f"   Score stuck at {score_history[0]} for 3 attempts. "
                  f"Converged — force-completing module.")
            return "complete_module"

    print(
        f"   Review FAILED (score={score}/{threshold}, "
        f"attempts={attempts}/{max_attempts}). Sending to fixer."
    )
    return "fixer"


# ─── WORKER SUBGRAPH ─────────────────────────────────────────

def _route_after_worker_review(state: WorkerState) -> Literal["worker_fixer", "worker_complete"]:
    score = state.get("review_score", 0) or 0
    attempts = state.get("fix_attempts", 0)
    max_att = state.get("max_fix_attempts", 3)
    threshold = state.get("review_threshold", 7)
    score_history = state.get("score_history", [])

    if score >= threshold:
        print(f"      ✓  Score {score}/10 — PASS")
        return "worker_complete"

    if attempts >= max_att:
        print(f"      ⚠  Max fix attempts ({attempts}/{max_att}) reached — force-complete")
        return "worker_complete"

    # Convergence detection
    if len(score_history) >= 3:
        recent = score_history[-3:]
        if len(set(recent)) == 1 and score < threshold:
            print(f"      ✗ Score stuck at {recent[0]}, converged — force-complete")
            return "worker_complete"

    print(f"      ✗ Score {score}/10, attempt {attempts}/{max_att} — RETRY")
    return "worker_fixer"


worker_builder = StateGraph(WorkerState)

worker_builder.add_node("worker_module_planner", worker_module_planner)
worker_builder.add_node("worker_coder", worker_coder)
worker_builder.add_node("worker_reviewer", worker_reviewer)
worker_builder.add_node("worker_fixer", worker_fixer)
worker_builder.add_node("worker_complete", worker_complete)

worker_builder.set_entry_point("worker_module_planner")
worker_builder.add_edge("worker_module_planner", "worker_coder")
worker_builder.add_edge("worker_coder", "worker_reviewer")

worker_builder.add_conditional_edges(
    "worker_reviewer",
    _route_after_worker_review,
    {
        "worker_fixer": "worker_fixer",
        "worker_complete": "worker_complete",
    },
)

worker_builder.add_edge("worker_fixer", "worker_reviewer")
worker_builder.add_edge("worker_complete", END)

worker_graph = worker_builder.compile()


def worker_entry_node(state: WorkerState) -> dict:
    result = worker_graph.invoke(state)

    return {
        "completed_modules": result.get("completed_modules", []),
        "generated_code": result.get("generated_code", {}),
        "tests": result.get("tests", {}),
    }


# ─── PARALLEL DISPATCHER ─────────────────────────────────────

def dispatcher_node(state: SoftwareState) -> dict:
    pending = state.get("pending_modules", [])
    max_concurrent = state.get("max_concurrent_modules", 5)

    if not pending:
        print("   No pending modules remaining.")
        return {"batch_modules": [], "current_module": None}

    batch = pending[:max_concurrent]
    remaining = pending[max_concurrent:]

    print("─" * 60)
    print(f"🚀  DISPATCHER: Spawning {len(batch)} parallel workers ({len(remaining)} remaining) …")
    for m in batch:
        print(f"   → Worker: {m}")

    return {
        "pending_modules": remaining,
        "batch_modules": batch,
    }


def _batch_sender_route(state: SoftwareState) -> list[Send]:
    """Return Send objects for the current batch of modules.

    Used as a conditional edge router on the batch_sender pass-through node."""
    batch = state.get("batch_modules", [])
    return [
        Send("worker_entry", _build_worker_payload(state, module))
        for module in batch
    ]


def route_after_dispatcher(state: SoftwareState) -> Literal["batch_sender", "human_review"]:
    batch = state.get("batch_modules", [])
    if batch:
        return "batch_sender"
    return "human_review"


def batch_check_node(state: SoftwareState) -> dict:
    """Fan-in point after parallel worker batch completes.

    LangGraph waits for ALL Send branches to finish before
    following the fixed edge to this node."""
    pending = state.get("pending_modules", [])
    modules = state.get("modules", [])
    completed = state.get("completed_modules", [])
    print(f"   Batch complete. {len(completed)}/{len(modules)} modules done. {len(pending)} remaining.")
    return {}


def route_after_batch_check(state: SoftwareState) -> Literal["dispatcher", "human_review"]:
    pending = state.get("pending_modules", [])
    if pending:
        return "dispatcher"
    return "human_review"


# ─── PARALLEL SANDBOX DISPATCHER ────────────────────────────

def _sandbox_route(state: SoftwareState) -> list[Send]:
    """Fan out to per-module sandbox workers.

    Used as a conditional edge router on the sandbox_dispatcher pass-through node."""
    completed = state.get("completed_modules", [])
    print("─" * 60)
    print(f"🧪  SANDBOX: Spawning sandbox workers for {len(completed)} modules …")
    for m in completed:
        print(f"   → Sandbox worker: {m}")

    return [
        Send("sandbox_worker_entry", _build_sandbox_worker_payload(state, module))
        for module in completed
    ]


def route_by_execution_mode(state: SoftwareState) -> Literal["dispatcher", "backend_lead"]:
    execution_mode = state.get("execution_mode", "parallel")
    if execution_mode == "parallel":
        print("   Execution mode: PARALLEL")
        return "dispatcher"
    print("   Execution mode: SEQUENTIAL (fallback)")
    return "backend_lead"


def route_after_human(state: SoftwareState) -> Literal["qa", "dispatcher", "backend_lead"]:
    if state.get("human_approved", False):
        print("\n✅ Human Approved. Proceeding to QA...\n")
        return "qa"

    print("\n🔄 Human requested regeneration. Re-dispatching...\n")
    execution_mode = state.get("execution_mode", "parallel")
    if execution_mode == "parallel":
        return "dispatcher"
    return "backend_lead"


# ─── MAIN GRAPH ──────────────────────────────────────────────

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

workflow.add_node("dispatcher", dispatcher_node)
workflow.add_node("batch_sender", lambda s: {})  # pass-through; routing handled by _batch_sender_route
workflow.add_node("worker_entry", worker_entry_node)
workflow.add_node("batch_check", batch_check_node)  # fan-in after parallel batch

workflow.add_node("human_review", human_review_node)
workflow.add_node("qa", qa_node)

# Human-in-the-loop routing
workflow.add_conditional_edges(
    "human_review",
    route_after_human,
    {
        "qa": "qa",
        "dispatcher": "dispatcher",
        "backend_lead": "backend_lead",
    },
)

workflow.add_node("sandbox_dispatcher", lambda s: {})  # pass-through; routing via _sandbox_route
workflow.add_node("sandbox_worker_entry", sandbox_worker_node)

workflow.add_node("sandbox_setup", sandbox_setup_node)
workflow.add_node("test_executor", test_executor_node)
workflow.add_node("test_fixer", test_fixer_node)
workflow.add_node("sandbox_cleanup", sandbox_cleanup_node)
workflow.add_node("file_writer", file_writer_node)
workflow.add_node("delivery", delivery_node)
workflow.add_node("project_reader", project_reader_node)
workflow.add_node("project_analyzer", project_analyzer_node)

# Entry: route by create_new / analyze / update

workflow.set_conditional_entry_point(
    route_by_mode,
    {
        "planner": "planner",
        "project_reader": "project_reader",
    },
)

workflow.add_edge("project_reader", "project_analyzer")
workflow.add_edge("project_analyzer", "planner")

# Up to project init — shared by both modes

workflow.add_edge("planner", "architect")
workflow.add_edge("architect", "quality_gen")
workflow.add_edge("quality_gen", "project_init")

# Mode selection: parallel dispatcher vs sequential backend_lead

workflow.add_conditional_edges(
    "project_init",
    route_by_execution_mode,
    {
        "dispatcher": "dispatcher",
        "backend_lead": "backend_lead",
    },
)

# ─── Parallel path ───────────────────────────────────────────

workflow.add_conditional_edges(
    "dispatcher",
    route_after_dispatcher,
    {
        "batch_sender": "batch_sender",
        "human_review": "human_review",
    },
)

workflow.add_conditional_edges(
    "batch_sender",
    _batch_sender_route,
    ["worker_entry"],
)

workflow.add_edge("worker_entry", "batch_check")  # fixed edge — waits for ALL Send branches

workflow.add_conditional_edges(
    "batch_check",
    route_after_batch_check,
    {
        "dispatcher": "dispatcher",
        "human_review": "human_review",
    },
)

# ─── Sequential path (fallback) ──────────────────────────────

workflow.add_conditional_edges(
    "backend_lead",
    route_after_backend_lead,
    {
        "module_planner": "module_planner",
        "human_review": "human_review",
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

# ─── QA + Sandbox (shared, parallel sandbox) ────────────────

workflow.add_conditional_edges(
    "qa",
    lambda s: "sandbox_dispatcher" if s.get("execution_mode") == "parallel" and s.get("sandbox_enabled") else "sandbox_setup",
    {
        "sandbox_dispatcher": "sandbox_dispatcher",
        "sandbox_setup": "sandbox_setup",
    },
)

# Parallel sandbox — per-module sandbox workers
workflow.add_conditional_edges(
    "sandbox_dispatcher",
    _sandbox_route,
    ["sandbox_worker_entry"],
)

# Sequential sandbox (fallback)
workflow.add_edge("sandbox_setup", "test_executor")

workflow.add_conditional_edges(
    "test_executor",
    lambda s: "file_writer" if not s.get("sandbox_path") else (
        "file_writer" if all(
            r.get("success", False) if isinstance(r, dict) else False
            for r in s.get("test_results", {}).values()
        ) else "test_fixer"
    ),
    {
        "file_writer": "file_writer",
        "test_fixer": "test_fixer",
    },
)

workflow.add_edge("test_fixer", "test_executor")

# Delivery (shared)

workflow.add_edge("sandbox_worker_entry", "delivery")  # parallel sandbox path
workflow.add_edge("file_writer", "sandbox_cleanup")
workflow.add_edge("sandbox_cleanup", "delivery")
workflow.add_edge("delivery", END)


memory = MemorySaver()
app = workflow.compile(checkpointer=memory)
