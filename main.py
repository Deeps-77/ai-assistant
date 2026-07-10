import os
import sys
import datetime
from graph import app
from state import SoftwareState
from config import WorkflowConfig
from observability.tracing import Tracer
from langgraph.types import Command


def config_to_initial_state(cfg: WorkflowConfig) -> SoftwareState:
    requirement = cfg.requirement

    if not requirement and cfg.mode.value in ("analyze", "update") and cfg.project_path:
        requirement = f"Analyze and improve the project at {cfg.project_path}"
    elif not requirement:
        requirement = "Build a web application"

    return {
        "requirement": requirement,
        "mode": cfg.mode.value,
        "tech_stack": cfg.tech_stack or None,
        "project_path": cfg.project_path,
        "output_dir": cfg.output_dir,
        "run_dir": os.path.join(cfg.output_dir, datetime.datetime.now().strftime("%Y%m%d_%H%M%S")),
        "max_fix_attempts": cfg.max_fix_attempts,
        "review_threshold": cfg.review_threshold,
        "adaptive_threshold": cfg.adaptive_threshold,
        "execution_mode": cfg.execution_mode,
        "max_concurrent_modules": cfg.max_concurrent_modules,
        "sandbox_enabled": cfg.sandbox_enabled,
        "sandbox_mode": cfg.sandbox_mode,
        "sandbox_docker_image": cfg.sandbox_docker_image,
        "sandbox_stack": None,
        "max_test_fix_attempts": cfg.max_test_fix_attempts,
        "provider": cfg.provider,
        "llm_base_url": cfg.llm_base_url,
        "llm_model": cfg.llm_model,
        "max_retries": cfg.max_retries,
        "stories": [],
        "architecture": None,
        "modules": [],
        "quality_guide": None,
        "pending_modules": [],
        "completed_modules": [],
        "batch_modules": [],
        "current_module": None,
        "module_plan": None,
        "generated_code": {},
        "tests": {},
        "review_score": None,
        "review_issues": [],
        "fix_attempts": 0,
        "score_history": [],
        "human_approved": False,
        "human_feedback": "",
        "existing_structure": None,
        "existing_code": {},
        "written_files": {},
        "delivery_package": None,
        "sandbox_path": None,
        "test_results": {},
        "test_fix_attempts": 0,
        "sandbox_cleanup_paths": [],
    }


HAS_FASTAPI = False
try:
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    import asyncio
    HAS_FASTAPI = True
except ImportError:
    pass


def _invoke_with_interrupts(initial_state, config, interactive):
    """Run the graph, surfacing/servicing human-in-the-loop interrupts.

    Returns the final state, or the (paused) state carrying ``__interrupt__``
    when running non-interactively and a human decision is required.
    """
    result = app.invoke(initial_state, config=config)
    while isinstance(result, dict) and (result.get("__interrupt__") or result.get("__interrupts__")):
        interrupts = result.get("__interrupt__") or result.get("__interrupts__")
        if not interactive:
            return result
        intr = interrupts[0]
        payload = getattr(intr, "value", intr)
        if isinstance(payload, dict):
            prompt = payload.get("prompt", "Approve Project? (yes/no): ")
        else:
            prompt = "Approve Project? (yes/no): "
        choice = input(prompt).strip().lower()
        feedback = ""
        if choice == "no":
            feedback = input("Enter feedback: ")
        result = app.invoke(
            Command(resume={"choice": choice, "feedback": feedback}),
            config=config,
        )
    return result


def run_workflow(cfg: WorkflowConfig, interactive: bool = True) -> SoftwareState:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    initial_state = config_to_initial_state(cfg)

    config = {
        "configurable": {"thread_id": cfg.thread_id},
        "recursion_limit": cfg.recursion_limit,
    }

    run_dir = initial_state.get("run_dir", os.path.join(cfg.output_dir, "run"))
    os.makedirs(run_dir, exist_ok=True)
    print(f"  Run Dir:      {run_dir}")

    print("=" * 60)
    print("AI SOFTWARE DELIVERY TEAM")
    print("=" * 60)
    print(f"  Mode:          {cfg.mode.value}")
    print(f"  Execution:     {cfg.execution_mode}")
    print(f"  Concurrency:   {cfg.max_concurrent_modules}")
    print(f"  Requirement:   {cfg.requirement[:100] if cfg.requirement else '(none)'}")
    print(f"  Project:       {cfg.project_path or '(will create)'}")
    print(f"  Tech Stack:    {cfg.tech_stack or '(auto-detect)'}")
    print(f"  LLM:           {cfg.llm_model}")
    print(f"  Thread:      {cfg.thread_id}")
    print("=" * 60 + "\n")

    from observability.tracing import Tracer, push_tracer, pop_tracer

    budget = float(os.getenv("OBSERVABILITY_BUDGET_USD", "0"))
    # Observability is on by default; disable with OBSERVABILITY_ENABLED=0.
    enabled = os.getenv("OBSERVABILITY_ENABLED", "1") != "0"
    tracer = Tracer(run_id=cfg.thread_id, enabled=enabled)
    tracer.global_budget_usd = budget or 0
    push_tracer(tracer)
    tracer.start_run(cfg.thread_id)
    try:
        result = _invoke_with_interrupts(initial_state, config, interactive)
    finally:
        tracer.end_run()
        pop_tracer()

    if isinstance(result, dict) and (result.get("__interrupt__") or result.get("__interrupts__")):
        print("\n⏸  WORKFLOW PAUSED — human review required (provide a decision to resume).")
        return result

    print("\n\n" + "=" * 60)
    print("WORKFLOW COMPLETE")
    print("=" * 60)

    print(f"\nModules Completed: {result['completed_modules']}")
    print(f"Total Code Files: {len(result['generated_code'])}")
    print(f"Files Written to Disk: {len(result.get('written_files', {}))}")

    written = result.get("written_files", {})
    if written:
        ok = sum(1 for v in written.values() if v == "ok")
        errors = sum(1 for v in written.values() if v != "ok")
        print(f"  Written: {ok} ok, {errors} errors")

    package = result.get("delivery_package", "")
    if package:
        print(f"\nDelivery package: {len(package)} chars")

    return result


def cli_main():
    cfg = WorkflowConfig.from_cli(sys.argv)
    run_workflow(cfg)


if HAS_FASTAPI:
    import asyncio
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    fastapi_app = FastAPI(title="AI Software Delivery")

    @fastapi_app.post("/run")
    async def run_workflow_endpoint(config: WorkflowConfig):
        loop = asyncio.get_event_loop()
        # Non-interactive: if a human review is required the graph pauses and
        # we return the interrupt payload instead of blocking on stdin.
        result = await loop.run_in_executor(None, run_workflow, config, False)
        interrupts = result.get("__interrupt__") or result.get("__interrupts__")
        if interrupts:
            return JSONResponse(status_code=202, content={
                "status": "paused",
                "interrupts": [getattr(i, "value", i) for i in interrupts],
            })
        serializable = dict(result)
        for k, v in serializable.items():
            if hasattr(v, "model_dump"):
                serializable[k] = v.model_dump()
        return JSONResponse(content=serializable)
else:
    fastapi_app = None


if __name__ == "__main__":
    cli_main()
