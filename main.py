import sys
from graph import app
from state import SoftwareState
from config import WorkflowConfig


def config_to_initial_state(cfg: WorkflowConfig) -> SoftwareState:
    requirement = cfg.requirement

    if not requirement and cfg.mode.value in ("analyze", "update") and cfg.project_path:
        requirement = f"Analyze and improve the project at {cfg.project_path}"
    elif not requirement:
        requirement = "Build a web application"

    return {
        "requirement": requirement,
        "mode": cfg.mode.value,
        "tech_stack": cfg.tech_stack or "",
        "project_path": cfg.project_path,
        "output_dir": cfg.output_dir,
        "max_fix_attempts": cfg.max_fix_attempts,
        "review_threshold": cfg.review_threshold,
        "provider": cfg.provider,
        "llm_base_url": cfg.llm_base_url,
        "llm_model": cfg.llm_model,
        "stories": [],
        "architecture": None,
        "modules": [],
        "quality_guide": None,
        "pending_modules": [],
        "completed_modules": [],
        "current_module": None,
        "module_plan": None,
        "generated_code": {},
        "tests": {},
        "review_score": None,
        "review_issues": [],
        "fix_attempts": 0,
        "existing_structure": None,
        "existing_code": {},
        "written_files": {},
        "delivery_package": None,
    }


HAS_FASTAPI = False
try:
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    import asyncio
    HAS_FASTAPI = True
except ImportError:
    pass


def run_workflow(cfg: WorkflowConfig) -> SoftwareState:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    initial_state = config_to_initial_state(cfg)

    config = {
        "configurable": {"thread_id": cfg.thread_id},
        "recursion_limit": cfg.recursion_limit,
    }

    print("=" * 60)
    print("AI SOFTWARE DELIVERY TEAM")
    print("=" * 60)
    print(f"  Mode:        {cfg.mode.value}")
    print(f"  Requirement: {cfg.requirement[:100] if cfg.requirement else '(none)'}")
    print(f"  Project:     {cfg.project_path or '(will create)'}")
    print(f"  Tech Stack:  {cfg.tech_stack or '(auto-detect)'}")
    print(f"  LLM:         {cfg.llm_model}")
    print(f"  Thread:      {cfg.thread_id}")
    print("=" * 60 + "\n")

    result = app.invoke(initial_state, config=config)

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
        result = await loop.run_in_executor(None, run_workflow, config)
        serializable = dict(result)
        for k, v in serializable.items():
            if hasattr(v, "model_dump"):
                serializable[k] = v.model_dump()
        return JSONResponse(content=serializable)
else:
    fastapi_app = None


if __name__ == "__main__":
    cli_main()
