import os
import json
import re
from typing import Any
from langchain_core.exceptions import OutputParserException
from dotenv import load_dotenv
from resilience import add_retry_to_llm

from state import (
    SoftwareState,
    WorkerState,
    SandboxWorkerState,
    ModuleList,
    ArchitectureDoc,
    ModulePlan,
    ModuleFile,
    CodeReview,
    ProjectAnalysis,
    TestResult,
    ExecutionPlan,
)
from sandbox_agent import (
    setup_sandbox as setup_sandbox_v2,
    run_tests_in_sandbox as run_tests_in_sandbox_v2,
    teardown_sandbox as teardown_sandbox_v2,
)
from sandbox_agent.context import SandboxContextV2
from sandbox_agent.environments.base import SandboxMode
from sandbox_agent.detector import detect_stack
from langgraph.types import interrupt
from prompts import (
    planner_prompt,
    planner_fallback_prompt,
    architect_prompt,
    architect_fallback_prompt,
    quality_guide_prompt,
    module_planner_prompt,
    module_planner_fallback_prompt,
    module_coder_prompt,
    reviewer_prompt,
    reviewer_fallback_prompt,
    fixer_prompt,
    qa_prompt,
    test_fixer_prompt,
    analyze_project_prompt,
    analysis_report_prompt,
    supervisor_prompt,
)
from file_tools import (
    extract_folder_structure_from_architecture,
    init_project_structure,
    ensure_directory,
    write_file,
    write_module_files,
    write_test_files,
    read_project_structure,
    read_project_files,
    parse_code_blocks,
    write_file_tool,
    create_directory_tool,
    read_file_tool,
)

load_dotenv()

# Maximum seconds to wait for a single LLM call before it times out.
# A hang otherwise blocks the whole graph; retries (resilience.py) still apply.
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "300"))

_llm_cache: dict = {}


def _make_json_llm(llm, pydantic_model):
    """Create a structured-output runnable WITHOUT using response_format.
    Works with local models that don't support OpenAI's structured output API."""
    import json
    import re
    from langchain_core.runnables import RunnableLambda
    from langchain_core.exceptions import OutputParserException

    def _parse(msg):
        text = msg.content if hasattr(msg, "content") else str(msg)
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if not json_match:
            raise OutputParserException(f"No JSON found in response for {pydantic_model.__name__}")
        try:
            data = json.loads(json_match.group())
            return pydantic_model(**data)
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            raise OutputParserException(f"Failed to parse {pydantic_model.__name__}: {e}")

    return llm | RunnableLambda(_parse)


def _get_llms(state: dict) -> dict[str, Any]:
    provider = state.get("provider", "ollama")
    base_url = state.get("llm_base_url", "https://ollama.com")
    model = state.get("llm_model") or os.getenv("LLM_MODEL") or os.getenv("OLLAMA_MODEL") or "gemma3:12b-cloud"
    max_retries = int(state.get("max_retries", 2))
    ctx_size = state.get("ctx_size")
    cache_key = f"{provider}:{base_url}:{model}:{ctx_size}"

    if cache_key in _llm_cache:
        return _llm_cache[cache_key]

    tools = [write_file_tool, create_directory_tool, read_file_tool]

    if provider == "lm_studio":
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(base_url=base_url, api_key="lm-studio",
                         model=model, temperature=0, timeout=LLM_TIMEOUT)
        add_retry_to_llm(llm, max_retries=max_retries)
        result = {
            "llm": llm,
            "tool_llm": llm.bind_tools(tools),
            "planner": _make_json_llm(llm, ModuleList),
            "architect": _make_json_llm(llm, ArchitectureDoc),
            "module_planner": _make_json_llm(llm, ModulePlan),
            "reviewer": _make_json_llm(llm, CodeReview),
            "analyzer": _make_json_llm(llm, ProjectAnalysis),
            "supervisor": _make_json_llm(llm, ExecutionPlan),
        }
    else:
        from langchain_ollama import ChatOllama
        ollama_kwargs = {"base_url": base_url, "model": model, "temperature": 0, "timeout": LLM_TIMEOUT}
        if ctx_size:
            ollama_kwargs["num_ctx"] = ctx_size
        llm = ChatOllama(**ollama_kwargs)
        add_retry_to_llm(llm, max_retries=max_retries)
        method = "json_mode"
        result = {
            "llm": llm,
            "tool_llm": llm.bind_tools(tools),
            "planner": llm.with_structured_output(ModuleList, method=method),
            "architect": llm.with_structured_output(ArchitectureDoc, method=method),
            "module_planner": llm.with_structured_output(ModulePlan, method=method),
            "reviewer": llm.with_structured_output(CodeReview, method=method),
            "analyzer": llm.with_structured_output(ProjectAnalysis, method=method),
            "supervisor": llm.with_structured_output(ExecutionPlan, method=method),
        }
    _llm_cache[cache_key] = result
    return result

# ═══════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════


def _dict_to_str(val) -> str:
    if isinstance(val, str):
        return val
    if isinstance(val, list):
        return "\n".join(f"- {_dict_to_str(v)}" for v in val)
    if isinstance(val, dict):
        return "\n".join(f"{k}: {_dict_to_str(v)}" for k, v in val.items())
    return str(val)


def _flatten_planner(raw: dict) -> ModuleList:
    stories = raw.get("stories") or raw.get("user_stories") or []
    modules = raw.get("modules") or raw.get("backend_modules") or raw.get("module_names") or []
    tech_stack = raw.get("tech_stack") or raw.get("stack") or raw.get("technology_stack") or ""
    return ModuleList(
        stories=[str(s) for s in stories],
        modules=[str(m) for m in modules],
        tech_stack=str(tech_stack),
    )


def _flatten_architecture(raw: dict) -> ArchitectureDoc:
    inner = raw
    for wrapper in ("system_architecture", "architecture", "arch"):
        if wrapper in raw and isinstance(raw[wrapper], dict):
            inner = raw[wrapper]
            break

    return ArchitectureDoc(
        tech_stack=_dict_to_str(inner.get("tech_stack", "")),
        db_schema=_dict_to_str(inner.get("db_schema", "")),
        api_endpoints=_dict_to_str(inner.get("api_endpoints", "")),
        folder_structure=_dict_to_str(inner.get("folder_structure", "")),
        architecture_diagram=_dict_to_str(inner.get("architecture_diagram", "")),
    )


def _flatten_module_plan(raw: dict) -> ModulePlan:
    name = raw.get("module_name") or raw.get("name") or ""
    files_raw = raw.get("files") or []
    files = []
    for f in files_raw:
        if isinstance(f, dict):
            exports_raw = f.get("exports") or []
            files.append(ModuleFile(
                path=f.get("path", ""),
                purpose=f.get("purpose", ""),
                exports=[str(e) for e in exports_raw],
            ))
    deps = raw.get("dependencies") or raw.get("deps") or []
    routes = raw.get("api_routes") or raw.get("routes") or []
    return ModulePlan(
        module_name=name,
        files=files,
        dependencies=[str(d) for d in deps],
        api_routes=[str(r) for r in routes],
    )


def _flatten_review(raw: dict) -> CodeReview:
    score = raw.get("score") or raw.get("quality_score") or 0
    if isinstance(score, str):
        score = int(score)

    issues_raw = raw.get("issues") or []
    issues = []
    for i in issues_raw:
        if isinstance(i, str):
            issues.append(i)
        elif isinstance(i, dict):
            issues.append(i.get("description") or i.get("message") or str(i))
        else:
            issues.append(str(i))

    logic = raw.get("logic_correctness") or raw.get("logic_correctness_analysis") or ""
    if isinstance(logic, dict):
        logic = _dict_to_str(logic)

    security = raw.get("security_check") or raw.get("security_analysis") or ""
    if isinstance(security, dict):
        security = _dict_to_str(security)

    return CodeReview(score=score, issues=issues, logic_correctness=logic, security_check=security)


# ═══════════════════════════════════════════════
# NODE 1 — PLANNER
# ═══════════════════════════════════════════════


def planner_node(state: SoftwareState):
    print("--- PLANNER: Analyzing Requirements ---")
    llms = _get_llms(state)

    prompt = planner_prompt()
    chain = prompt | llms["planner"]

    try:
        result: ModuleList = chain.invoke({
            "requirement": state["requirement"],
            "human_feedback": state.get("human_feedback", "") or "",
        })
    except (OutputParserException, TypeError, ValueError, KeyError):
        print("   Planner structured output failed; attempting fallback...")
        try:
            raw_response = llms["llm"].invoke(
                planner_fallback_prompt().format(requirement=state["requirement"])
            )
        except Exception:
            print("   Planner fallback LLM call also failed; using safe defaults.")
            return {
                "stories": [f"Implement {state['requirement']}"],
                "modules": ["app"],
                "tech_stack": state.get("tech_stack") or "Python/FastAPI",
                "pending_modules": ["app"],
                "completed_modules": [],
                "max_fix_attempts": state.get("max_fix_attempts", 3),
                "review_threshold": state.get("review_threshold", 7),
            }
        try:
            raw_dict = json.loads(raw_response.content)
        except json.JSONDecodeError:
            print("   Planner fallback JSON parse failed; using safe defaults.")
            return {
                "stories": [f"Implement {state['requirement']}"],
                "modules": ["app"],
                "tech_stack": state.get("tech_stack") or "Python/FastAPI",
                "pending_modules": ["app"],
                "completed_modules": [],
                "max_fix_attempts": state.get("max_fix_attempts", 3),
                "review_threshold": state.get("review_threshold", 7),
            }
        result = _flatten_planner(raw_dict)

    clean_modules = []
    for m in result.modules:
        if isinstance(m, str):
            clean_modules.append(m)
        elif isinstance(m, dict):
            clean_modules.append(m.get("name", str(m)))
        else:
            clean_modules.append(str(m))

    tech_stack = state.get("tech_stack") or result.tech_stack or "Python/FastAPI"

    print(f"   Stories: {len(result.stories)} | Modules: {clean_modules} | Stack: {tech_stack}")

    return {
        "stories": result.stories,
        "modules": clean_modules,
        "tech_stack": tech_stack,
        "pending_modules": clean_modules,
        "completed_modules": [],
        "max_fix_attempts": state.get("max_fix_attempts", 3),
        "review_threshold": state.get("review_threshold", 7),
    }


# ═══════════════════════════════════════════════
# NODE 2 — ARCHITECT
# ═══════════════════════════════════════════════


def architect_node(state: SoftwareState):
    tech_stack = state.get("tech_stack") or "Python/FastAPI"
    print(f"--- ARCHITECT: Designing System ({tech_stack}) ---")
    llms = _get_llms(state)

    prompt = architect_prompt()
    chain = prompt | llms["architect"]

    try:
        doc: ArchitectureDoc = chain.invoke({
            "tech_stack": tech_stack,
            "stories": state["stories"],
            "modules": state["modules"],
        })
    except (OutputParserException, TypeError, ValueError, KeyError):
        print("   Architect structured output failed; attempting fallback...")
        try:
            raw_response = llms["llm"].invoke(
                architect_fallback_prompt().format(
                    tech_stack=tech_stack,
                    stories=state["stories"],
                    modules=state["modules"],
                )
            )
        except Exception:
            print("   Architect fallback LLM call also failed; using safe defaults.")
            raw_dict = {}
        else:
            try:
                raw_dict = json.loads(raw_response.content)
            except json.JSONDecodeError:
                print("   Architect fallback JSON parse failed; using safe defaults.")
                raw_dict = {}
        doc = _flatten_architecture(raw_dict)

    arch_str = f"""# Architecture Document

## Tech Stack
{doc.tech_stack}

## Database Schema
{doc.db_schema}

## API Endpoints
{doc.api_endpoints}

## Folder Structure
{doc.folder_structure}

## Architecture Diagram
{doc.architecture_diagram}
"""
    print(f"   Tech stack: {doc.tech_stack}")
    return {"architecture": arch_str}


# ═══════════════════════════════════════════════
# NODE 2b — QUALITY GUIDE GENERATOR
# ═══════════════════════════════════════════════


def quality_gen_node(state: SoftwareState):
    tech_stack = state.get("tech_stack") or "Python/FastAPI"
    print(f"--- QUALITY: Generating quality guide for {tech_stack} ---")
    llms = _get_llms(state)

    chain = quality_guide_prompt() | llms["llm"]
    try:
        response = chain.invoke({"tech_stack": tech_stack})
    except Exception:
        print("   Quality guide LLM call failed; using fallback.")
        guide = f"# Quality Guide for {tech_stack}\n- Follow best practices for {tech_stack}\n"
        print(f"   Quality guide generated ({len(guide)} chars)")
        return {"quality_guide": guide}

    guide = response.content or ""
    if not guide.strip():
        guide = f"# Quality Guide for {tech_stack}\n- Follow best practices for {tech_stack}\n"
        print("   Quality guide empty; using fallback.")

    print(f"   Quality guide generated ({len(guide)} chars)")
    return {"quality_guide": guide}


# ═══════════════════════════════════════════════
# NODE 2c — PROJECT INIT
# ═══════════════════════════════════════════════


def _flatten_execution_plan(raw: dict) -> dict:
    d = raw if isinstance(raw, dict) else {}

    def _as_bool(v, default: bool = False) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in ("true", "1", "yes", "y")
        return default

    def _as_int(v, default: int) -> int:
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    mode = str(d.get("execution_mode", "parallel")).lower()
    review_threshold = max(1, min(10, _as_int(d.get("review_threshold"), 7)))
    max_fix = max(1, _as_int(d.get("max_fix_attempts"), 3))

    return {
        "pause_for_plan_approval": _as_bool(d.get("pause_for_plan_approval"), False),
        "skip_build": _as_bool(d.get("skip_build"), False),
        "skip_tests": _as_bool(d.get("skip_tests"), False),
        "execution_mode": "sequential" if mode.startswith("seq") else "parallel",
        "review_threshold": review_threshold,
        "max_fix_attempts": max_fix,
        "security_focus": _as_bool(d.get("security_focus"), False),
        "notes": str(d.get("notes", "")),
    }


def _default_execution_plan(plan_mode: bool) -> dict:
    return {
        "pause_for_plan_approval": bool(plan_mode),
        "skip_build": False,
        "skip_tests": False,
        "execution_mode": "parallel",
        "review_threshold": 7,
        "max_fix_attempts": 3,
        "security_focus": False,
        "notes": "Default full delivery plan (supervisor unavailable).",
    }


def supervisor_node(state: SoftwareState):
    """Decide the delivery graph flow from the requirement.

    Produces an :class:`ExecutionPlan` (stored as a dict in state) that the
    graph routers consult to dynamically choose stages, strictness, and whether
    to pause for plan approval before building.
    """
    print("--- SUPERVISOR: Deciding execution plan ---")
    plan_mode = bool(state.get("plan_mode", False))
    llms = _get_llms(state)
    sup_llm = llms.get("supervisor")

    if sup_llm is None:
        print(f"   No supervisor LLM available; using default plan (plan_mode={plan_mode}).")
        plan = _default_execution_plan(plan_mode)
    else:
        chain = supervisor_prompt() | sup_llm
        try:
            result = chain.invoke({
                "requirement": state.get("requirement", ""),
                "plan_mode": str(plan_mode),
            })
            if hasattr(result, "model_dump"):
                raw = result.model_dump()
            elif isinstance(result, dict):
                raw = result
            else:
                raw = {}
            plan = _flatten_execution_plan(raw)
        except (OutputParserException, TypeError, ValueError, KeyError):
            print("   Supervisor structured output failed; using default plan.")
            plan = _default_execution_plan(plan_mode)

    # Plan mode (opencode-style /plan toggle) always pauses for plan approval.
    if plan_mode:
        plan["pause_for_plan_approval"] = True

    print(f"   Plan: mode={plan['execution_mode']} review>={plan['review_threshold']} "
          f"pause={plan['pause_for_plan_approval']} skip_build={plan['skip_build']} "
          f"skip_tests={plan['skip_tests']} security={plan['security_focus']}")
    if plan.get("notes"):
        print(f"   Notes: {plan['notes']}")

    return {
        "execution_plan": plan,
        "execution_mode": plan["execution_mode"],
        "review_threshold": plan["review_threshold"],
        "max_fix_attempts": plan["max_fix_attempts"],
        "skip_tests": plan["skip_tests"],
        "security_focus": plan["security_focus"],
    }


def _parse_plan_decision(decision) -> tuple[str, str]:
    """Extract (choice, feedback) from the resume value.

    The CLI/`main.py` path resumes with ``{"choice": "yes", "feedback": ""}``,
    while the wrapped assistant (REPL/server) routes the decision through the
    outer agent's ``{"decisions": [{...}]}`` envelope, so accept both.
    """
    if isinstance(decision, dict):
        choice = decision.get("choice")
        feedback = decision.get("feedback", "") or ""
        if choice is None and isinstance(decision.get("decisions"), list) and decision["decisions"]:
            inner = decision["decisions"][0]
            if isinstance(inner, dict):
                choice = inner.get("choice")
                feedback = inner.get("feedback", "") or ""
        choice = str(choice or "").strip().lower()
        feedback = str(feedback or "")
        return choice, feedback
    return str(decision or "").strip().lower(), ""


def _format_plan(state: SoftwareState, plan: dict) -> str:
    lines = []
    stories = state.get("stories", []) or []
    modules = state.get("modules", []) or []
    arch = state.get("architecture", "") or ""
    lines.append(f"Requirement: {state.get('requirement', '')}")
    lines.append(f"Tech stack: {state.get('tech_stack', '')}")
    lines.append(f"Modules ({len(modules)}): {', '.join(modules) if modules else '(none)'}")
    if stories:
        lines.append("User stories:")
        for s in stories[:12]:
            lines.append(f"  - {s}")
    if arch:
        snippet = arch.strip().splitlines()[:15]
        lines.append("Architecture (excerpt):")
        lines.extend(f"  {ln}" for ln in snippet)
    lines.append(
        f"Execution: {plan.get('execution_mode')} | review>={plan.get('review_threshold')} "
        f"| tests={'skip' if plan.get('skip_tests') else 'run'} "
        f"| security_focus={plan.get('security_focus')}"
    )
    return "\n".join(lines)


def plan_review_node(state: SoftwareState):
    """opencode-style plan gate.

    If the supervisor (or plan mode) requested plan approval, surface the plan
    and pause for the user. On approval, continue to build (or deliver a
    plan-only result). On rejection, loop back to the planner with feedback.
    """
    plan = state.get("execution_plan") or {}

    if not plan.get("pause_for_plan_approval", False):
        # No approval requested (e.g. normal build) — pass straight through.
        return {}

    print("\n" + "=" * 60)
    print("📋 PLAN REVIEW (approval required before building)")
    print("=" * 60)
    print(_format_plan(state, plan))

    decision = interrupt({
        "type": "plan_review",
        "prompt": "Approve this plan before building? (yes/no): ",
        "plan": _format_plan(state, plan),
    })

    if isinstance(decision, dict):
        choice = str(decision.get("choice", "")).strip().lower()
        feedback = decision.get("feedback", "") or ""
    else:
        choice = str(decision).strip().lower()
        feedback = ""

    if choice == "no":
        print("   Plan rejected. Regenerating plan with feedback.")
        return {
            "plan_rejected": True,
            "plan_approved": False,
            "plan_reviews_completed": 1,
            "human_feedback": feedback,
            "pending_modules": list(state.get("modules", [])),
            "completed_modules": [],
            "generated_code": {},
            "tests": {},
        }

    print("   Plan approved.")
    return {"plan_rejected": False, "plan_approved": True, "plan_reviews_completed": 1}


def project_init_node(state: SoftwareState):
    project_path = state.get("project_path") or os.path.join(
        state.get("output_dir", "outputs"), "project"
    )
    tech_stack = state.get("tech_stack") or "Python/FastAPI"
    print(f"--- INIT: Creating project skeleton at {project_path} ---")

    folder_structure = extract_folder_structure_from_architecture(
        state.get("architecture", "")
    )

    if not folder_structure:
        print("   No folder structure in architecture; creating minimal directories.")
        ensure_directory(project_path)
        return {"project_path": project_path}

    print(f"   Asking LLM to create directory structure via tool calls...")

    llms = _get_llms(state)
    prompt_text = (
        f"You are creating the project directory structure for a {tech_stack} project.\n"
        f"The project root is: {project_path}\n\n"
        f"Create the following directory structure by calling `create_directory_tool` "
        f"for each directory. Start every path from the project root.\n\n"
        f"{folder_structure}\n\n"
        f"Call `create_directory_tool` for every directory in the tree."
    )

    try:
        response = llms["tool_llm"].invoke(prompt_text)
        written, _ = _execute_tool_calls(response, project_path, label="init")
        if written:
            print(f"   Tool calls created {len(written)} directories")
        else:
            # Fallback: parse and create programmatically
            print("   No tool calls received; falling back to programmatic directory creation.")
            init_project_structure(project_path, folder_structure)
    except Exception as e:
        print(f"   LLM tool call failed ({e}); falling back to programmatic creation.")
        init_project_structure(project_path, folder_structure)

    return {"project_path": project_path}


# ═══════════════════════════════════════════════
# NODE 3 — BACKEND LEAD (Dispatcher)
# ═══════════════════════════════════════════════


def backend_lead_node(state: SoftwareState):
    print("--- BACKEND LEAD: Assigning Work ---")

    pending = list(state.get("pending_modules", []))

    if not pending:
        print("   No pending modules remaining.")
        return {"current_module": None}

    next_module = pending[0]
    new_pending = pending[1:]

    if isinstance(next_module, dict):
        next_module = next_module.get("name", str(next_module))

    print(f"   Assigning: {next_module}  (remaining: {len(new_pending)})")

    return {
        "current_module": next_module,
        "pending_modules": new_pending,
    }


# ═══════════════════════════════════════════════
# NODE 4a — MODULE PLANNER
# ═══════════════════════════════════════════════


def module_planner_node(state: SoftwareState):
    module = state["current_module"]
    tech_stack = state.get("tech_stack") or "Python/FastAPI"
    print(f"--- MODULE PLANNER: Planning [{module}] ({tech_stack}) ---")
    llms = _get_llms(state)

    prompt = module_planner_prompt()
    chain = prompt | llms["module_planner"]
    quality = state.get("quality_guide", "")

    try:
        plan: ModulePlan = chain.invoke({
            "tech_stack": tech_stack,
            "module": module,
            "architecture": state["architecture"],
            "quality_guide": quality,
        })
    except (OutputParserException, TypeError, ValueError, KeyError):
        print("   Module planner structured output failed; attempting fallback...")
        try:
            raw_response = llms["llm"].invoke(
                module_planner_fallback_prompt().format(module=module, architecture=state.get("architecture", ""))
            )
        except Exception:
            print("   Module planner fallback LLM call also failed; using empty plan.")
            raw_dict = {}
        else:
            try:
                raw_dict = json.loads(raw_response.content)
            except json.JSONDecodeError:
                print("   Module planner fallback JSON parse failed; using empty plan.")
                raw_dict = {}
        plan = _flatten_module_plan(raw_dict)

    plan_lines = [f"## Plan for {plan.module_name}"]
    plan_lines.append(f"\n### Files:")
    for f in plan.files:
        exports = ", ".join(f.exports) if hasattr(f, "exports") and f.exports else ""
        plan_lines.append(f"- {f.path}: {f.purpose} [{exports}]")
    plan_lines.append(f"\n### Dependencies: {', '.join(plan.dependencies)}")
    plan_lines.append(f"\n### API Routes:")
    for r in plan.api_routes:
        plan_lines.append(f"- {r}")

    return {"module_plan": "\n".join(plan_lines)}


# ═══════════════════════════════════════════════
# NODE 4b — MODULE CODER
# ═══════════════════════════════════════════════


def _extract_paths_from_plan(module_plan: str) -> list[str]:
    paths: list[str] = []
    for line in module_plan.split("\n"):
        line = line.strip()
        if line.startswith("- ") and ":" in line:
            path = line[2:].split(":")[0].strip()
            if path and (path.endswith(".py") or "." in path):
                paths.append(path)
    return paths


def _execute_tool_calls(response, project_path: str, label: str = "") -> tuple[dict[str, str], dict[str, str]]:
    """Execute tool calls from an LLM response and return (written_files, code_map).

    written_files: rel_path -> status string
    code_map: rel_path -> content for tracking
    """
    written: dict[str, str] = {}
    code_blocks: dict[str, str] = {}

    has_calls = hasattr(response, "tool_calls") and bool(response.tool_calls)
    content_len = len((response.content or "").strip()) if hasattr(response, "content") else -1
    prefix = f"   [{label}] " if label else "   "
    print(f"{prefix}response: tool_calls={has_calls}, text_len={content_len}")

    if has_calls:
        for tc in response.tool_calls:
            name = tc.get("name", "")
            args = tc.get("args", {})
            print(f"{prefix}  tool: {name} -> {args.get('filepath') or args.get('path', '')}")
            if name == "write_file_tool":
                rel_path = args.get("filepath", "")
                content = args.get("content", "")
                if rel_path:
                    try:
                        full_path = os.path.join(project_path, rel_path)
                        result = write_file(full_path, content)
                        written[rel_path.replace("\\", "/")] = result
                        code_blocks[rel_path.replace("\\", "/")] = content
                    except Exception as e:
                        print(f"{prefix}  write_file failed for {rel_path}: {e}")
                        written[rel_path.replace("\\", "/")] = f"error: {e}"
            elif name == "create_directory_tool":
                dir_path = args.get("path", "")
                if dir_path:
                    try:
                        full_path = os.path.join(project_path, dir_path)
                        ensure_directory(full_path)
                        written[dir_path.replace("\\", "/") + "/"] = "ok"
                    except Exception as e:
                        print(f"{prefix}  create_directory failed for {dir_path}: {e}")
                        written[dir_path.replace("\\", "/") + "/"] = f"error: {e}"
    else:
        print(f"{prefix}  (no tool calls in response)")
    return written, code_blocks


def module_coder_node(state: SoftwareState):
    module = state["current_module"]
    tech_stack = state.get("tech_stack") or "Python/FastAPI"
    project_path = state.get("project_path") or os.path.join(
        state.get("output_dir", "outputs"), "project"
    )
    print(f"--- MODULE CODER: Coding [{module}] ({tech_stack}) ---")
    llms = _get_llms(state)

    module_plan = state.get("module_plan", "")
    planned_paths = _extract_paths_from_plan(module_plan)
    exact_file_paths = "\n".join(f"  - {p}" for p in planned_paths) if planned_paths else module_plan

    prompt = module_coder_prompt()
    chain = prompt | llms["tool_llm"]
    try:
        response = chain.invoke({
            "tech_stack": tech_stack,
            "module": module,
            "architecture": state["architecture"],
            "exact_file_paths": exact_file_paths,
            "quality_guide": state.get("quality_guide", ""),
            "human_feedback": state.get("human_feedback", ""),
        })

        # Try tool calling path first
        written_files, tool_code_blocks = _execute_tool_calls(response, project_path, label="code")

        if tool_code_blocks:
            code_map = dict(state.get("generated_code", {}))
            combined = "\n\n".join(
                f"# --- {path} ---\n{content}"
                for path, content in tool_code_blocks.items()
            )
            code_map[module] = combined

            if planned_paths:
                generated = list(tool_code_blocks.keys())
                missing = [p for p in planned_paths if p not in generated]
                extra = [p for p in generated if p not in planned_paths]
                if missing:
                    print(f"   WARNING: {len(missing)} planned files missing:")
                    for p in missing:
                        print(f"     MISSING: {p}")
                if extra:
                    print(f"   WARNING: {len(extra)} unexpected files:")
                    for p in extra:
                        print(f"     EXTRA: {p}")

            print(f"   Tool calls: {len(written_files)} file(s) written")
            return {
                "generated_code": code_map,
                "written_files": dict(state.get("written_files", {}), **written_files),
                "fix_attempts": 0,
            }

        # Tool calls exist but none wrote files (e.g. only create_directory_tool)
        if hasattr(response, "tool_calls") and response.tool_calls:
            print(f"   Tool calls created dirs only; re-prompting tool_llm with file write instruction...")
            reinforced_hf = (
                "IMPORTANT: You MUST use the write_file_tool to write actual code files "
                "with their full content. Creating directories alone is not enough. "
                "Every file listed in the plan must be written using write_file_tool."
            )
            response2 = chain.invoke({
                "tech_stack": tech_stack,
                "module": module,
                "architecture": state["architecture"],
                "exact_file_paths": exact_file_paths,
                "quality_guide": state.get("quality_guide", ""),
                "human_feedback": reinforced_hf,
            })
            written_files2, tool_code_blocks2 = _execute_tool_calls(response2, project_path, label="code")
            if tool_code_blocks2:
                code_map = dict(state.get("generated_code", {}))
                combined = "\n\n".join(
                    f"# --- {path} ---\n{content}"
                    for path, content in tool_code_blocks2.items()
                )
                code_map[module] = combined
                print(f"   Tool calls (retry): {len(written_files2)} file(s) written")
                return {
                    "generated_code": code_map,
                    "written_files": dict(state.get("written_files", {}), **written_files2),
                    "fix_attempts": 0,
                }

        # Fallback: text-based approach
        content = response.content or ""
        if not content.strip():
            print(f"   Empty response from tool_llm; retrying with plain LLM...")
            try:
                response = (prompt | llms["llm"]).invoke({
                    "tech_stack": tech_stack,
                    "module": module,
                    "architecture": state["architecture"],
                    "exact_file_paths": exact_file_paths,
                    "quality_guide": state.get("quality_guide", ""),
                    "human_feedback": state.get("human_feedback", ""),
                })
                content = response.content or ""
            except Exception:
                content = ""
            if not content.strip():
                print(f"   Empty response for [{module}]; generating placeholder.")
                content = f"# {module} module\n# TODO: implement\n"

        code_map = dict(state.get("generated_code", {}))
        code_map[module] = content

        generated_paths = list(parse_code_blocks(content).keys())
        if planned_paths and generated_paths:
            missing = [p for p in planned_paths if p not in generated_paths]
            extra = [p for p in generated_paths if p not in planned_paths]
            if missing:
                print(f"   WARNING: {len(missing)} planned files missing from output:")
                for p in missing:
                    print(f"     MISSING: {p}")
            if extra:
                print(f"   WARNING: {len(extra)} unexpected files in output:")
                for p in extra:
                    print(f"     EXTRA: {p}")
            if missing or extra:
                print(f"   Planned: {planned_paths}")
                print(f"   Generated: {generated_paths}")

        return {
            "generated_code": code_map,
            "fix_attempts": 0,
        }

    except Exception:
        print(f"   Module coder LLM call failed for [{module}]; using placeholder.")
        content = f"# {module} module\n# TODO: implement\n"
        code_map = dict(state.get("generated_code", {}))
        code_map[module] = content
        return {"generated_code": code_map, "fix_attempts": 0}


# ═══════════════════════════════════════════════
# NODE 5 — REVIEWER
# ═══════════════════════════════════════════════


def reviewer_node(state: SoftwareState):
    module = state["current_module"]
    code = state["generated_code"].get(module, "")
    tech_stack = state.get("tech_stack") or "Python/FastAPI"
    print(f"--- REVIEWER: Reviewing [{module}] ({tech_stack}) ---")
    llms = _get_llms(state)

    if not code:
        print(f"   No code found for [{module}]; returning failing review.")
        return {
            "review_score": 1,
            "review_issues": [f"No code generated for module '{module}'"],
        }

    prompt = reviewer_prompt()
    chain = prompt | llms["reviewer"]

    try:
        review: CodeReview = chain.invoke({
            "tech_stack": tech_stack,
            "module": module,
            "code": code,
            "security_focus": str(bool(state.get("security_focus", False))),
        })
    except (OutputParserException, TypeError, ValueError, KeyError):
        print("   Review structured output failed; attempting fallback...")
        try:
            raw_response = llms["llm"].invoke(
                reviewer_fallback_prompt().format(tech_stack=tech_stack, module=module, code=code)
            )
        except Exception:
            print("   Review fallback LLM call also failed; using safe defaults.")
            raw_dict = {}
        else:
            try:
                raw_dict = json.loads(raw_response.content)
            except json.JSONDecodeError:
                print("   Review fallback JSON parse failed; using safe defaults.")
                raw_dict = {}
        review = _flatten_review(raw_dict)

    print(f"   Score: {review.score}/10 | Issues: {len(review.issues)}")
    for issue in review.issues:
        print(f"     * {issue}")

    score_hist = list(state.get("score_history", []))
    score_hist.append(review.score)

    return {
        "review_score": review.score,
        "review_issues": review.issues,
        "score_history": score_hist,
    }


# ═══════════════════════════════════════════════
# NODE 6 — FIXER
# ═══════════════════════════════════════════════


def fixer_node(state: SoftwareState):
    module = state["current_module"]
    code = state["generated_code"].get(module, "")
    issues = state.get("review_issues", [])
    attempts = state.get("fix_attempts", 0) + 1
    tech_stack = state.get("tech_stack") or "Python/FastAPI"
    project_path = state.get("project_path") or os.path.join(
        state.get("output_dir", "outputs"), "project"
    )

    print(f"--- FIXER: Fixing [{module}] (attempt {attempts}) ({tech_stack}) ---")
    llms = _get_llms(state)

    quality = state.get("quality_guide", "")

    prompt = fixer_prompt()
    chain = prompt | llms["tool_llm"]
    try:
        response = chain.invoke({
            "tech_stack": tech_stack,
            "module": module,
            "code": code,
            "issues": "\n".join(f"- {i}" for i in issues),
            "quality_guide": quality,
            "human_feedback": state.get("human_feedback", ""),
        })

        # Try tool calling path first
        written_files, tool_code_blocks = _execute_tool_calls(response, project_path, label="fix")

        if tool_code_blocks:
            code_map = dict(state["generated_code"])
            combined = "\n\n".join(
                f"# --- {path} ---\n{content}"
                for path, content in tool_code_blocks.items()
            )
            code_map[module] = combined
            written = dict(state.get("written_files", {}))
            written.update(written_files)
            return {
                "generated_code": code_map,
                "written_files": written,
                "fix_attempts": attempts,
            }

        # Tool calls exist but none wrote files (e.g. only create_directory_tool)
        if hasattr(response, "tool_calls") and response.tool_calls:
            print(f"   Fix tool calls created dirs only; re-prompting tool_llm...")
            reinforced_hf = (
                "IMPORTANT: You MUST use the write_file_tool to write the fixed code files "
                "with their full content. Creating directories alone is not enough."
            )
            response2 = chain.invoke({
                "tech_stack": tech_stack,
                "module": module,
                "code": code,
                "issues": "\n".join(f"- {i}" for i in issues),
                "quality_guide": quality,
                "human_feedback": reinforced_hf,
            })
            written_files2, tool_code_blocks2 = _execute_tool_calls(response2, project_path, label="fix")
            if tool_code_blocks2:
                code_map = dict(state["generated_code"])
                combined = "\n\n".join(
                    f"# --- {path} ---\n{content}"
                    for path, content in tool_code_blocks2.items()
                )
                code_map[module] = combined
                written = dict(state.get("written_files", {}))
                written.update(written_files2)
                return {
                    "generated_code": code_map,
                    "written_files": written,
                    "fix_attempts": attempts,
                }

        # Fallback: text-based response
        text = (response.content or "").strip()
        if not text:
            print(f"   Empty fix from tool_llm; retrying with plain LLM...")
            try:
                response = (prompt | llms["llm"]).invoke({
                    "tech_stack": tech_stack,
                    "module": module,
                    "code": code,
                    "issues": "\n".join(f"- {i}" for i in issues),
                    "quality_guide": quality,
                    "human_feedback": state.get("human_feedback", ""),
                })
                text = (response.content or "").strip()
            except Exception:
                text = ""
            if not text:
                print(f"   Fixer produced nothing for [{module}]; keeping original code.")
                code_map = dict(state["generated_code"])
                return {
                    "generated_code": code_map,
                    "fix_attempts": attempts,
                }

        code_map = dict(state["generated_code"])
        code_map[module] = text
        return {
            "generated_code": code_map,
            "fix_attempts": attempts,
        }

    except Exception:
        print(f"   Fixer LLM call failed for [{module}]; keeping original code.")
        code_map = dict(state["generated_code"])
        return {
            "generated_code": code_map,
            "fix_attempts": attempts,
        }


# ═══════════════════════════════════════════════
# NODE 7 — COMPLETE MODULE
# ═══════════════════════════════════════════════


def _rebuild_project_dirs(state: SoftwareState) -> None:
    project_path = state.get("project_path", "")
    if not project_path:
        return

    arch_structure = extract_folder_structure_from_architecture(
        state.get("architecture", "")
    )

    actual_dirs: set[str] = set()
    for module_code in state.get("generated_code", {}).values():
        for file_path in parse_code_blocks(module_code):
            parts = file_path.replace("\\", "/").split("/")
            for i in range(1, len(parts)):
                actual_dirs.add("/".join(parts[:i]))

    if actual_dirs:
        merged = "\n".join(
            f"{d}/" if not d.startswith(".") else d
            for d in sorted(actual_dirs | set(
                d for d in [
                    l.strip("- ").split(":")[0].strip()
                    for l in arch_structure.split("\n")
                    if l.strip().startswith("- ") and "/" in l
                ] if d
            ))
        )
        init_project_structure(project_path, merged)


def complete_module_node(state: SoftwareState):
    module = state["current_module"]
    print(f"--- COMPLETE: Marking [{module}] as done ---")

    completed = list(state.get("completed_modules", []))
    if module and module not in completed:
        completed.append(module)

    print(f"   Completed so far: {completed}")

    _rebuild_project_dirs(state)

    return {
        "completed_modules": completed,
        "current_module": None,
        "module_plan": None,
        "review_score": None,
        "review_issues": [],
        "fix_attempts": 0,
        "score_history": [],
    }


# ═══════════════════════════════════════════════
# NODE 7b — HUMAN REVIEW (Human-in-the-Loop)
# ═══════════════════════════════════════════════


def human_review_node(state: SoftwareState):

    print("\n" + "=" * 60)
    print("👤 HUMAN IN THE LOOP")
    print("=" * 60)

    print("\n📦 Completed Modules:")
    for module in state.get("completed_modules", []):
        print(f"✔ {module}")

    print("\n📄 Generated Modules:")
    for module in state.get("generated_code", {}).keys():
        print(f"✔ {module}")

    print(f"\n📝 Requirement:\n  {state.get('requirement', '')[:200]}")

    # Pause the graph and surface a decision to the client. On resume this
    # call returns the value provided via Command(resume=...). Works headless
    # and with the FastAPI server (no blocking stdin read).
    decision = interrupt({
        "type": "human_review",
        "prompt": "Approve Project? (yes/no): ",
        "completed_modules": state.get("completed_modules", []),
    })

    if isinstance(decision, dict):
        choice = str(decision.get("choice", "")).strip().lower()
        feedback = decision.get("feedback", "") or ""
    else:
        choice = str(decision).strip().lower()
        feedback = ""

    if choice == "no":
        return {
            "human_approved": False,
            "human_feedback": feedback,
            "completed_modules": [],
            "generated_code": {},
            "tests": {},
            "pending_modules": state.get("modules", []),
        }

    return {
        "human_approved": True,
        "human_feedback": "",
    }


# ═══════════════════════════════════════════════
# NODE 8 — QA AGENT
# ═══════════════════════════════════════════════


def qa_node(state: SoftwareState):
    tech_stack = state.get("tech_stack") or "Python/FastAPI"
    execution_mode = state.get("execution_mode", "parallel")
    sandbox_enabled = state.get("sandbox_enabled", False)

    # In parallel+sandbox mode, tests are generated inside each
    # sandbox_worker_node concurrently.  Only the sequential path
    # needs tests generated here.
    if execution_mode == "parallel" and sandbox_enabled:
        print(f"--- QA AGENT: Tests deferred to parallel sandbox workers ---")
        return {}

    print(f"--- QA AGENT: Generating Tests ({tech_stack}) ---")
    llms = _get_llms(state)

    tests: dict[str, str] = {}

    for module, code in state["generated_code"].items():
        print(f"   Generating tests for [{module}]...")

        prompt = qa_prompt()
        chain = prompt | llms["llm"]
        try:
            response = chain.invoke({
                "tech_stack": tech_stack,
                "module": module,
                "code": code,
            })
        except Exception:
            print(f"   Test generation LLM call failed for [{module}]; skipping.")
            tests[module] = f"# Tests for {module}\n# TODO: add tests\n"
            continue
        tests[module] = response.content

    print(f"   Tests generated for {len(tests)} modules.")
    return {"tests": tests}


# ═══════════════════════════════════════════════
# NODE 8a — SANDBOX SETUP
# ═══════════════════════════════════════════════


def sandbox_setup_node(state: SoftwareState):
    project_path = state.get("project_path", "")
    if not state.get("sandbox_enabled", False):
        print("--- SANDBOX: Disabled, skipping ---")
        return {"sandbox_path": None}

    if not project_path:
        print("--- SANDBOX: No project_path set, skipping ---")
        return {"sandbox_path": None}

    mode_str = state.get("sandbox_mode", "local")
    docker_image = state.get("sandbox_docker_image", None)
    tech_stack_hint = state.get("tech_stack", "")

    stack = detect_stack(project_path, tech_stack_hint)
    print(f"--- SANDBOX: Setting up isolated {stack.name} sandbox for {project_path} ---")

    try:
        smode = SandboxMode(mode_str)
        v2_ctx, logs = setup_sandbox_v2(project_path, mode=smode, docker_image=docker_image)
        for log in logs:
            print(log)

        cleanup_paths = list(state.get("sandbox_cleanup_paths", []))
        cleanup_paths.append(v2_ctx.temp_dir)

        return {
            "sandbox_path": v2_ctx.temp_dir,
            "sandbox_stack": stack.name,
            "sandbox_cleanup_paths": cleanup_paths,
        }
    except (RuntimeError, OSError) as e:
        print(f"   Sandbox setup failed: {e}")
        return {"sandbox_path": None}


# ═══════════════════════════════════════════════
# NODE 8b — TEST EXECUTOR
# ═══════════════════════════════════════════════


def _rebuild_sandbox_context(sandbox_path: str, stack_name: str = "python") -> SandboxContextV2:
    from sandbox_agent.environments.python_env import PythonEnvironment
    from sandbox_agent.environments.node_env import NodeEnvironment
    from sandbox_agent.environments.rust_env import RustEnvironment
    from sandbox_agent.environments.go_env import GoEnvironment

    env_map = {
        "python": PythonEnvironment,
        "node": NodeEnvironment,
        "rust": RustEnvironment,
        "go": GoEnvironment,
    }
    env_cls = env_map.get(stack_name, PythonEnvironment)
    env = env_cls()

    project_dir = os.path.join(sandbox_path, "project")

    if stack_name == "python":
        venv_dir = os.path.join(sandbox_path, ".venv")
        if os.name == "nt":
            venv_python = os.path.join(venv_dir, "Scripts", "python.exe")
            venv_pip = os.path.join(venv_dir, "Scripts", "pip.exe")
        else:
            venv_python = os.path.join(venv_dir, "bin", "python")
            venv_pip = os.path.join(venv_dir, "bin", "pip")
    else:
        venv_python = ""
        venv_pip = ""

    ctx = SandboxContextV2(
        temp_dir=sandbox_path,
        project_dir=project_dir,
        stack_name=stack_name,
        env=env,
    )
    ctx.extra["venv_python"] = venv_python
    ctx.extra["venv_pip"] = venv_pip
    return ctx


def test_executor_node(state: SoftwareState):
    sandbox_path = state.get("sandbox_path")
    if not sandbox_path or not os.path.isdir(sandbox_path):
        print("--- TEST EXECUTOR: No sandbox available, skipping ---")
        return {"test_results": {}}

    stack_name = state.get("sandbox_stack", "python")
    print(f"--- TEST EXECUTOR: Running {stack_name} tests in sandbox ---")

    try:
        context = _rebuild_sandbox_context(sandbox_path, stack_name)
    except Exception as e:
        print(f"   Failed to rebuild sandbox context: {e}")
        return {"test_results": {}}

    tests = state.get("tests", {})

    if not tests:
        print("   No tests to execute.")
        return {"test_results": {}}

    test_files_written = 0
    for module, test_content in tests.items():
        parsed = parse_code_blocks(test_content)
        if parsed:
            for rel_path, content in parsed.items():
                full_path = os.path.join(context.project_dir, rel_path.replace("\\", "/"))
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)
                test_files_written += 1
        else:
            if stack_name == "python":
                test_path = os.path.join(context.project_dir, f"test_{module}.py")
            elif stack_name == "node":
                test_path = os.path.join(context.project_dir, f"{module}.test.js")
            elif stack_name == "rust":
                test_path = os.path.join(context.project_dir, "tests", f"{module}.rs")
            elif stack_name == "go":
                test_path = os.path.join(context.project_dir, f"{module}_test.go")
            else:
                test_path = os.path.join(context.project_dir, f"test_{module}.py")
            os.makedirs(os.path.dirname(test_path), exist_ok=True)
            with open(test_path, "w", encoding="utf-8") as f:
                f.write(test_content)
            test_files_written += 1

    print(f"   Wrote {test_files_written} test file(s) to sandbox.")

    results: dict[str, TestResult] = {}

    for module in tests:
        print(f"   Running tests for [{module}]...")
        result_data = run_tests_in_sandbox_v2(context)
        result = TestResult(**result_data)
        results[module] = result

        status = "PASS" if result.success else "FAIL"
        print(f"     [{status}] {result.passed} passed, {result.failed} failed, {result.errors} errors")

    return {"test_results": {k: v.model_dump() for k, v in results.items()}}


# ═══════════════════════════════════════════════
# NODE 8c — TEST FIXER
# ═══════════════════════════════════════════════


def test_fixer_node(state: SoftwareState):
    tech_stack = state.get("tech_stack") or "Python/FastAPI"
    attempts = state.get("test_fix_attempts", 0) + 1
    print(f"--- TEST FIXER: Fixing failing tests (attempt {attempts}) ({tech_stack}) ---")
    llms = _get_llms(state)

    test_results = state.get("test_results", {})
    failing_modules = [
        m for m, r in test_results.items()
        if isinstance(r, dict) and not r.get("success", False)
    ]

    if not failing_modules:
        print("   No failing modules found.")
        return {"test_fix_attempts": attempts}

    fixed_code = dict(state.get("generated_code", {}))
    fixed_tests = dict(state.get("tests", {}))

    for module in failing_modules:
        code = fixed_code.get(module, "")
        tests = fixed_tests.get(module, "")
        test_output = test_results.get(module, {}).get("output", "")

        print(f"   Fixing [{module}] based on test failures...")

        prompt = test_fixer_prompt()
        chain = prompt | llms["llm"]
        try:
            response = chain.invoke({
                "tech_stack": tech_stack,
                "module": module,
                "code": code,
                "tests": tests,
                "test_output": test_output,
            })
        except Exception:
            print(f"     Test fixer LLM call failed for [{module}]; keeping existing code/tests.")
            continue

        content = response.content or ""
        if not content.strip():
            print(f"     Empty fix response for [{module}]")
            continue

        parsed_files = parse_code_blocks(content)
        if parsed_files:
            code_parts: list[str] = []
            test_parts: list[str] = []
            for file_path, file_content in parsed_files.items():
                path_lower = file_path.replace("\\", "/").lower()
                is_test = (
                    path_lower.startswith("test_")
                    or "/test_" in path_lower
                    or path_lower.startswith("tests/")
                    or "/tests/" in path_lower
                )
                if is_test:
                    test_parts.append(f"# --- {file_path} ---\n```\n{file_content}\n```")
                else:
                    code_parts.append(f"# --- {file_path} ---\n```\n{file_content}\n```")
            if code_parts:
                fixed_code[module] = "\n\n".join(code_parts)
            if test_parts:
                fixed_tests[module] = "\n\n".join(test_parts)
            print(f"     Fixed {len(parsed_files)} file(s) for [{module}] "
                  f"({len(code_parts)} code, {len(test_parts)} test)")
        else:
            fixed_tests[module] = content
            print(f"     Updated tests for [{module}] (no file headers detected)")

    return {
        "generated_code": fixed_code,
        "tests": fixed_tests,
        "test_fix_attempts": attempts,
    }


# ═══════════════════════════════════════════════
# NODE 8e — SANDBOX CLEANUP
# ═══════════════════════════════════════════════


def sandbox_cleanup_node(state: SoftwareState):
    cleanup_paths = state.get("sandbox_cleanup_paths", [])
    if not cleanup_paths:
        print("--- SANDBOX CLEANUP: Nothing to clean up ---")
        return {}

    import shutil

    cleaned = 0
    failed = 0
    for path in cleanup_paths:
        try:
            shutil.rmtree(path, ignore_errors=True)
            cleaned += 1
        except Exception as e:
            print(f"  Warning: failed to clean up {path}: {e}")
            failed += 1

    print(f"--- SANDBOX CLEANUP: Cleaned {cleaned} temp dir(s)" +
          (f" ({failed} failed)" if failed else "") + " ---")
    return {"sandbox_cleanup_paths": [], "sandbox_path": None}


# ═══════════════════════════════════════════════
# NODE 8d — FILE WRITER
# ═══════════════════════════════════════════════


def file_writer_node(state: SoftwareState):
    project_path = state.get("project_path", "")
    if not project_path:
        print("   No project_path set. Skipping file writes.")
        return {}

    print(f"--- FILE WRITER: Writing code to {project_path} ---")
    written: dict[str, str] = {}

    for module, code in state.get("generated_code", {}).items():
        results = write_module_files(project_path, module, code,
                                     state.get("architecture", ""))
        written.update(results)

    test_results = write_test_files(project_path, state.get("tests", {}))
    written.update(test_results)

    ok_count = sum(1 for v in written.values() if v == "ok")
    error_count = sum(1 for v in written.values() if v != "ok")
    print(f"   Files written: {ok_count} ok, {error_count} errors")

    return {"written_files": written}


# ═══════════════════════════════════════════════
# NODE 9 — DELIVERY PACKAGE
# ═══════════════════════════════════════════════


def delivery_node(state: SoftwareState):
    print("--- DELIVERY: Compiling Package ---")

    tech_stack = state.get("tech_stack") or "Python/FastAPI"

    sections = []
    sections.append("# ═══════════════════════════════════════════")
    sections.append("# SOFTWARE DELIVERY PACKAGE")
    sections.append("# ═══════════════════════════════════════════\n")

    sections.append("## Requirement\n")
    sections.append(state["requirement"])

    sections.append(f"\n## Tech Stack\n{tech_stack}")

    sections.append("\n## User Stories\n")
    for s in state.get("stories", []):
        sections.append(f"- {s}")

    sections.append("\n## Completed Modules\n")
    for m in state.get("completed_modules", []):
        sections.append(f"- {m}")

    sections.append(f"\n## Architecture\n")
    sections.append(state.get("architecture", "N/A"))

    if state.get("written_files"):
        sections.append("\n## Written Files\n")
        for path, status in state.get("written_files", {}).items():
            sections.append(f"- {path} [{status}]")

    sections.append("\n\n## ═══ SOURCE CODE ═══\n")
    for module, code in state.get("generated_code", {}).items():
        sections.append(f"\n### Module: {module}\n")
        sections.append(code)

    sections.append("\n\n## ═══ TEST CODE ═══\n")
    for module, test in state.get("tests", {}).items():
        sections.append(f"\n### Tests: {module}\n")
        sections.append(test)

    package = "\n".join(sections)

    output_dir = state.get("output_dir", "outputs")
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "delivery_package.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(package)

    print(f"   Package saved to {filepath} ({len(package)} chars)")
    return {"delivery_package": package}


# ═══════════════════════════════════════════════
# NODE 10 — PROJECT READER
# ═══════════════════════════════════════════════


def project_reader_node(state: SoftwareState):
    project_path = state.get("project_path", "")
    if not project_path or not os.path.isdir(project_path):
        print(f"   Project path not found: {project_path}")
        return {
            "existing_structure": f"[Project path not found: {project_path}]",
            "existing_code": {},
        }

    print(f"--- READER: Reading project at {project_path} ---")

    structure = read_project_structure(project_path)
    files = read_project_files(project_path)

    print(f"   Files read: {len(files)}")
    return {
        "existing_structure": structure,
        "existing_code": files,
    }


# ═══════════════════════════════════════════════
# NODE 11 — PROJECT ANALYZER
# ═══════════════════════════════════════════════


def project_analyzer_node(state: SoftwareState):
    print("--- ANALYZER: Analyzing existing project ---")
    llms = _get_llms(state)

    existing_files = state.get("existing_code", {})
    files_preview = "\n\n".join(
        f"--- {path} ---\n{content[:2000]}"
        for path, content in list(existing_files.items())[:10]
    )

    chain = analyze_project_prompt() | llms["analyzer"]

    try:
        analysis: ProjectAnalysis = chain.invoke({
            "structure": state.get("existing_structure", ""),
            "files": files_preview,
            "requirement": state.get("requirement", ""),
        })
    except (OutputParserException, TypeError, ValueError, KeyError):
        print("   Analyzer structured output failed; returning minimal analysis.")
        analysis = ProjectAnalysis(
            tech_stack=state.get("tech_stack", "Unknown"),
            modules=list(existing_files.keys()),
            missing_modules=[],
            issues=[],
            architecture_summary="",
        )
        return {
            "tech_stack": analysis.tech_stack,
            "modules": analysis.modules,
            "analysis": analysis,
            "stories": state.get("stories", []),
            "pending_modules": analysis.modules,
            "quality_guide": None,
        }

    print(f"   Detected stack: {analysis.tech_stack}")
    print(f"   Existing modules: {analysis.modules}")
    print(f"   Missing modules: {analysis.missing_modules}")

    stories = []
    if analysis.architecture_summary:
        stories.append(f"Maintain existing architecture: {analysis.architecture_summary[:100]}")
    for m in analysis.missing_modules:
        stories.append(f"Add missing module: {m}")
    for issue in analysis.issues[:3]:
        stories.append(f"Fix issue: {issue}")

    return {
        "tech_stack": analysis.tech_stack,
        "modules": analysis.modules + analysis.missing_modules,
        "analysis": analysis,
        "stories": stories or state.get("stories", []),
        "pending_modules": analysis.missing_modules or analysis.modules,
        "quality_guide": None,
    }


def analysis_report_node(state: SoftwareState):
    """Turn a `ProjectAnalysis` into a readable prose report (read-only).

    Used by `analyze` mode so the pipeline reports on an existing project
    instead of regenerating its code.
    """
    print("--- REPORT: Composing project analysis report ---")
    analysis: Optional[ProjectAnalysis] = state.get("analysis")
    if analysis is None:
        return {
            "delivery_package": "No analysis was produced for this project.",
            "analysis_report": "No analysis was produced for this project.",
        }

    llms = _get_llms(state)
    chain = analysis_report_prompt() | llms["llm"]

    report = chain.invoke({
        "tech_stack": analysis.tech_stack,
        "modules": ", ".join(analysis.modules) or "(none detected)",
        "missing_modules": ", ".join(analysis.missing_modules) or "(none)",
        "issues": "\n".join(f"- {i}" for i in analysis.issues) or "(none)",
        "architecture_summary": analysis.architecture_summary or "(no summary)",
    })

    text = report.content if hasattr(report, "content") else str(report)
    return {
        "delivery_package": text,
        "analysis_report": text,
    }


# ═══════════════════════════════════════════════════════════════
# PARALLEL WORKER SUBGRAPH NODES
# ═══════════════════════════════════════════════════════════════


def _build_worker_payload(state: SoftwareState, module_name: str) -> WorkerState:
    return WorkerState(
        module_name=module_name,
        requirement=state["requirement"],
        architecture=state.get("architecture", ""),
        stories=state.get("stories", []),
        quality_guide=state.get("quality_guide"),
        tech_stack=state.get("tech_stack") or "Python/FastAPI",
        project_path=state.get("project_path") or os.path.join(
            state.get("output_dir", "outputs"), "project"
        ),
        provider=state.get("provider", "ollama"),
        llm_base_url=state.get("llm_base_url", "https://ollama.com"),
        llm_model=state.get("llm_model") or os.getenv("LLM_MODEL") or os.getenv("OLLAMA_MODEL") or "gemma3:12b-cloud",
        module_plan=None,
        generated_code={},
        tests={},
        review_score=None,
        review_issues=[],
        fix_attempts=0,
        max_fix_attempts=state.get("max_fix_attempts", 3),
        review_threshold=state.get("review_threshold", 7),
        human_approved=state.get("human_approved", False),
        human_feedback=state.get("human_feedback", ""),
        completed_modules=[],
    )


def worker_module_planner(state: WorkerState) -> dict:
    module = state["module_name"]
    print(f"   [plan] [{module}] Module Planner (parallel) …")
    llms = _get_llms(state)

    prompt = module_planner_prompt()

    try:
        result: ModulePlan = (prompt | llms["module_planner"]).invoke({
            "tech_stack": state["tech_stack"],
            "module": module,
            "architecture": state.get("architecture", ""),
            "quality_guide": state.get("quality_guide", ""),
        })
    except (OutputParserException, Exception) as exc:
        print(f"      * [{module}] Module planner failed ({exc}); using default plan.")
        plan_text = f"Module: {module}\nFiles: [{module}/routes.py, {module}/models.py, {module}/schemas.py, {module}/crud.py]\nDependencies: [fastapi, sqlalchemy]\nRoutes: [GET /{module}, POST /{module}]"
        return {"module_plan": plan_text}

    plan_lines = [f"## Plan for {result.module_name}"]
    plan_lines.append("\n### Files:")
    for f in result.files:
        exports = ", ".join(f.exports) if f.exports else ""
        plan_lines.append(f"- {f.path}: {f.purpose} [{exports}]")
    plan_lines.append(f"\n### Dependencies: {', '.join(result.dependencies)}")
    plan_lines.append("\n### API Routes:")
    for r in result.api_routes:
        plan_lines.append(f"- {r}")

    return {"module_plan": "\n".join(plan_lines)}


def worker_coder(state: WorkerState) -> dict:
    module = state["module_name"]
    tech_stack = state["tech_stack"]
    project_path = state.get("project_path") or ""
    print(f"   [code] [{module}] Coder generating code (parallel) …")
    llms = _get_llms(state)

    module_plan = state.get("module_plan", "")
    planned_paths = []
    for line in module_plan.split("\n"):
        line = line.strip()
        if line.startswith("- ") and ":" in line:
            path = line[2:].split(":")[0].strip()
            if path and (path.endswith(".py") or "." in path):
                planned_paths.append(path)

    exact_file_paths = "\n".join(f"  - {p}" for p in planned_paths) if planned_paths else module_plan

    prompt = module_coder_prompt()

    try:
        response = (prompt | llms["tool_llm"]).invoke({
            "tech_stack": tech_stack,
            "module": module,
            "architecture": state.get("architecture", ""),
            "exact_file_paths": exact_file_paths,
            "quality_guide": state.get("quality_guide", ""),
            "human_feedback": state.get("human_feedback", ""),
        })

        # Try tool calling path first
        written_files, tool_code_blocks = _execute_tool_calls(response, project_path, label="w_code")

        if tool_code_blocks:
            combined = "\n\n".join(
                f"# --- {path} ---\n{content}"
                for path, content in tool_code_blocks.items()
            )
            return {"generated_code": {module: combined}, "written_files": written_files}

        # Tool calls exist but none wrote files (e.g. only create_directory_tool)
        if hasattr(response, "tool_calls") and response.tool_calls:
            print(f"      * [{module}] Tool calls created dirs only; re-prompting tool_llm...")
            reinforced_hf = (
                "IMPORTANT: You MUST use the write_file_tool to write actual code files "
                "with their full content. Creating directories alone is not enough. "
                "Every file listed in the plan must be written using write_file_tool."
            )
            response2 = (prompt | llms["tool_llm"]).invoke({
                "tech_stack": tech_stack,
                "module": module,
                "architecture": state.get("architecture", ""),
                "exact_file_paths": exact_file_paths,
                "quality_guide": state.get("quality_guide", ""),
                "human_feedback": reinforced_hf,
            })
            written_files2, tool_code_blocks2 = _execute_tool_calls(response2, project_path, label="w_code")
            if tool_code_blocks2:
                combined = "\n\n".join(
                    f"# --- {path} ---\n{content}"
                    for path, content in tool_code_blocks2.items()
                )
                return {"generated_code": {module: combined}, "written_files": written_files2}

        # Fallback: text-based response
        content = response.content or ""
        if not content.strip():
            print(f"      * [{module}] Empty from tool_llm; retrying with plain LLM...")
            try:
                response = (prompt | llms["llm"]).invoke({
                    "tech_stack": tech_stack,
                    "module": module,
                    "architecture": state.get("architecture", ""),
                    "exact_file_paths": exact_file_paths,
                    "quality_guide": state.get("quality_guide", ""),
                    "human_feedback": state.get("human_feedback", ""),
                })
                content = response.content or ""
            except Exception:
                content = ""
            if not content.strip():
                content = f"# {module} module\n# TODO: implement\n"

        return {"generated_code": {module: content}}

    except Exception:
        print(f"      * [{module}] Coder LLM call failed; using placeholder.")
        return {"generated_code": {module: f"# {module} module\n# TODO: implement\n"}}


def worker_reviewer(state: WorkerState) -> dict:
    module = state["module_name"]
    code = state["generated_code"].get(module, "")
    tech_stack = state["tech_stack"]
    print(f"   [review] [{module}] Reviewer (attempt {state.get('fix_attempts', 0) + 1}) …")
    llms = _get_llms(state)

    if not code:
        print(f"      * No code to review for [{module}].")
        return {"review_score": 1, "review_issues": [f"No code generated for '{module}'"]}

    prompt = reviewer_prompt()

    try:
        review: CodeReview = (prompt | llms["reviewer"]).invoke({
            "tech_stack": tech_stack,
            "module": module,
            "code": code,
            "security_focus": str(bool(state.get("security_focus", False))),
        })
    except (OutputParserException, Exception) as exc:
        print(f"      * [{module}] Reviewer failed ({exc}); defaulting score=5.")
        review = CodeReview(score=5, issues=[str(exc)], logic_correctness="unknown", security_check="unknown")

    if review.score > 10:
        review.score = round(review.score / 10)
    review.score = max(1, min(review.score, 10))

    print(f"      Score: {review.score}/10 | Issues: {len(review.issues)}")
    for iss in review.issues[:3]:
        print(f"        * {iss}")

    score_hist = list(state.get("score_history", []))
    score_hist.append(review.score)

    return {"review_score": review.score, "review_issues": review.issues, "score_history": score_hist}


def worker_fixer(state: WorkerState) -> dict:
    module = state["module_name"]
    tech_stack = state["tech_stack"]
    attempts = state.get("fix_attempts", 0) + 1
    code = state["generated_code"].get(module, "")
    issues = state.get("review_issues", [])
    project_path = state.get("project_path") or ""
    print(f"   [fix] [{module}] Fixer (attempt {attempts}) …")
    llms = _get_llms(state)

    prompt = fixer_prompt()

    try:
        response = (prompt | llms["tool_llm"]).invoke({
            "tech_stack": tech_stack,
            "module": module,
            "code": code,
            "issues": "\n".join(f"- {i}" for i in issues),
            "quality_guide": state.get("quality_guide", ""),
            "human_feedback": state.get("human_feedback", ""),
        })

        # Try tool calling path first
        written_files, tool_code_blocks = _execute_tool_calls(response, project_path, label="w_fix")

        if tool_code_blocks:
            combined = "\n\n".join(
                f"# --- {path} ---\n{content}"
                for path, content in tool_code_blocks.items()
            )
            return {"generated_code": {module: combined}, "fix_attempts": attempts, "written_files": written_files}

        # Tool calls exist but none wrote files (e.g. only create_directory_tool)
        if hasattr(response, "tool_calls") and response.tool_calls:
            print(f"      * [{module}] Fix tool calls created dirs only; re-prompting tool_llm...")
            reinforced_hf = (
                "IMPORTANT: You MUST use the write_file_tool to write the fixed code files "
                "with their full content. Creating directories alone is not enough."
            )
            response2 = (prompt | llms["tool_llm"]).invoke({
                "tech_stack": tech_stack,
                "module": module,
                "code": code,
                "issues": "\n".join(f"- {i}" for i in issues),
                "quality_guide": state.get("quality_guide", ""),
                "human_feedback": reinforced_hf,
            })
            written_files2, tool_code_blocks2 = _execute_tool_calls(response2, project_path, label="w_fix")
            if tool_code_blocks2:
                combined = "\n\n".join(
                    f"# --- {path} ---\n{content}"
                    for path, content in tool_code_blocks2.items()
                )
                return {"generated_code": {module: combined}, "fix_attempts": attempts, "written_files": written_files2}

        # Fallback: text-based response
        text = (response.content or "").strip()
        if not text:
            print(f"      * [{module}] Empty fix from tool_llm; retrying with plain LLM...")
            try:
                response = (prompt | llms["llm"]).invoke({
                    "tech_stack": tech_stack,
                    "module": module,
                    "code": code,
                    "issues": "\n".join(f"- {i}" for i in issues),
                    "quality_guide": state.get("quality_guide", ""),
                    "human_feedback": state.get("human_feedback", ""),
                })
                text = (response.content or "").strip()
            except Exception:
                text = ""
            if not text:
                print(f"      * [{module}] Fixer produced nothing; keeping original code.")
                return {"generated_code": state.get("generated_code", {}), "fix_attempts": attempts}

        return {"generated_code": {module: text}, "fix_attempts": attempts}

    except Exception:
        print(f"      * [{module}] Fixer LLM call failed; keeping original code.")
        return {"generated_code": state.get("generated_code", {}), "fix_attempts": attempts}


def worker_complete(state: WorkerState) -> dict:
    module = state["module_name"]
    score = state.get("review_score", 0) or 0
    print(f"   [done] [{module}] Complete (parallel, final score={score})")

    return {
        "completed_modules": [module],
        "generated_code": state.get("generated_code", {}),
        "tests": state.get("tests", {}),
    }


# ═══════════════════════════════════════════════════════════════
# PARALLEL SANDBOX WORKER
# ═══════════════════════════════════════════════════════════════


def _build_sandbox_worker_payload(state: SoftwareState, module_name: str) -> SandboxWorkerState:
    return SandboxWorkerState(
        module_name=module_name,
        project_path=state.get("project_path", ""),
        tech_stack=state.get("tech_stack") or "Python/FastAPI",
        output_dir=state.get("output_dir", "outputs"),
        run_dir=state.get("run_dir", "outputs/run"),
        generated_code={module_name: state.get("generated_code", {}).get(module_name, "")},
        tests={module_name: state.get("tests", {}).get(module_name, "")},
        sandbox_enabled=state.get("sandbox_enabled", False),
        sandbox_mode=state.get("sandbox_mode", "local"),
        sandbox_docker_image=state.get("sandbox_docker_image", None),
        provider=state.get("provider", "ollama"),
        llm_base_url=state.get("llm_base_url", "https://ollama.com"),
        llm_model=state.get("llm_model") or os.getenv("LLM_MODEL") or os.getenv("OLLAMA_MODEL") or "gemma3:12b-cloud",
        sandbox_stack=state.get("sandbox_stack", None),
        sandbox_path=None,
        test_results={},
        test_fix_attempts=0,
        max_test_fix_attempts=state.get("max_test_fix_attempts", 3),
        written_files={},
        sandbox_cleanup_paths=[],
    )


_REQUIRED_FILES = {
    "django": ["manage.py"],
    "python": [],
    "fastapi": [],
    "node": ["package.json"],
    "express": ["package.json"],
    "react": ["package.json"],
    "rust": ["Cargo.toml"],
    "go": ["go.mod"],
}


def _check_testability(project_dir: str, tech_stack: str) -> tuple[bool, str]:
    tech_lower = tech_stack.lower()
    tech_words = set(tech_lower.replace("/", " ").replace("-", " ").replace("_", " ").split())
    for stack_key, files in _REQUIRED_FILES.items():
        if stack_key in tech_words:
            missing = [f for f in files if not os.path.exists(os.path.join(project_dir, f))]
            if missing:
                return False, f"Missing required files: {', '.join(missing)}"
    return True, ""


_FATAL_PATTERNS = [
    (r"ModuleNotFoundError|ImportError|No module named", "FATAL_DEPENDENCY"),
    (r"ImproperlyConfigured|django\.core\.exceptions", "FATAL_CONFIG"),
    (r"OperationalError|ConnectionRefused|can't connect", "FATAL_DATABASE"),
    (r"SyntaxError|IndentationError|TabError", "FATAL_SYNTAX"),
    (r"No such file or directory|FileNotFoundError", "FATAL_MISSING_FILE"),
    (r"Got an error creating the test database", "FATAL_DATABASE"),
]


def _classify_error(output: str) -> str:
    for pattern, error_type in _FATAL_PATTERNS:
        if re.search(pattern, output, re.IGNORECASE):
            return error_type
    return "FIXABLE"


def _log_failure(run_dir: str, module: str, error_type: str, details: str,
                 attempts: int, output: str):
    import datetime
    log_path = os.path.join(run_dir, "test_failures.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write(f"FAILURE REPORT - {timestamp}\n")
        f.write("=" * 80 + "\n")
        f.write(f"Module: {module}\n")
        f.write(f"Error type: {error_type}\n")
        f.write(f"Details: {details}\n")
        f.write(f"Fix attempts: {attempts}\n")
        if output:
            truncated = output[:1500]
            f.write(f"Latest output:\n{truncated}\n")
            if len(output) > 1500:
                f.write("... (truncated)\n")
        f.write("-" * 80 + "\n\n")


def _llm_logic_review(state: SandboxWorkerState, module: str,
                       code_content: str, test_content: str,
                       tech_stack: str) -> tuple[bool, list[str]]:
    from langchain_core.prompts import ChatPromptTemplate
    try:
        llms = _get_llms(state)
        prompt = ChatPromptTemplate.from_template(
            "Review this code and its tests for the '{module}' module ({tech_stack}).\n\n"
            "Code:\n{code}\n\n"
            "Tests:\n{tests}\n\n"
            "Check for:\n"
            "1. Syntax errors in both code and tests\n"
            "2. Import correctness (do the imports match the code?)\n"
            "3. Logical consistency between code and tests\n"
            "4. Common issues (undefined variables, mismatched function signatures)\n\n"
            "Return ONLY a JSON object with exactly these keys:\n"
            '- "has_issues": true or false\n'
            '- "issues": array of strings describing each issue found\n'
            '- "summary": one-line summary\n\n'
            '{{"has_issues": false, "issues": [], "summary": "No issues found."}}'
        )
        messages = prompt.format_messages(
            module=module,
            tech_stack=tech_stack,
            code=code_content[:3000],
            tests=test_content[:3000],
        )
        response = llms["llm"].invoke(messages)
        match = re.search(r"\{.*\}", response.content, re.DOTALL)
        if match:
            data = json.loads(match.group())
            has_issues = data.get("has_issues", True)
            issues = data.get("issues", ["LLM review could not be parsed"])
            return has_issues, issues
    except Exception as e:
        return True, [f"LLM logic review failed: {e}"]
    return True, ["LLM review returned no parsable result"]


def sandbox_worker_node(state: SandboxWorkerState) -> dict:
    module = state["module_name"]
    project_path = state["project_path"]
    tech_stack = state["tech_stack"]
    sandbox_enabled = state.get("sandbox_enabled", False)
    output_dir = state.get("output_dir", "outputs")
    run_dir = state.get("run_dir", os.path.join(output_dir, "run"))

    print(f"   [sandbox] [{module}] Sandbox worker (parallel) ...")

    if not project_path:
        print(f"      No project_path; writing files to output dir.")
        project_path = os.path.join(output_dir, "project")

    code_content = state.get("generated_code", {}).get(module, "")
    test_content = state.get("tests", {}).get(module, "")

    # Generate tests on the fly if qa_node deferred them (parallel mode)
    if not test_content and code_content:
        print(f"   [sandbox] [{module}] Generating tests...")
        llms = _get_llms(state)
        from prompts import qa_prompt as _qa_prompt
        try:
            response = (_qa_prompt() | llms["llm"]).invoke({
                "tech_stack": tech_stack,
                "module": module,
                "code": code_content,
            })
            test_content = response.content or ""
        except Exception:
            print(f"   [sandbox] [{module}] Test gen failed; using placeholder.")
            test_content = f"# Tests for {module}\n# TODO: add tests\n"

    written: dict[str, str] = {}

    if code_content:
        parsed_code = parse_code_blocks(code_content)
        if parsed_code:
            for rel_path, content in parsed_code.items():
                full_path = os.path.join(project_path, rel_path.replace("\\", "/"))
                status = write_file(full_path, content)
                written[rel_path.replace("\\", "/")] = status
        else:
            module_dir = os.path.join(project_path, module)
            os.makedirs(module_dir, exist_ok=True)
            filepath = os.path.join(module_dir, f"{module}.py")
            status = write_file(filepath, code_content)
            written[os.path.relpath(filepath, project_path).replace("\\", "/")] = status

    if not sandbox_enabled:
        print(f"      Sandbox disabled; writing code files only.")
        if test_content:
            filepath = os.path.join(project_path, f"test_{module}.py")
            status = write_file(filepath, test_content)
            written[f"test_{module}.py"] = status
        return {
            "test_results": {},
            "written_files": written,
        }

    test_results: dict[str, Any] = {}
    test_fix_attempts = state.get("test_fix_attempts", 0)
    max_test_fix_attempts = state.get("max_test_fix_attempts", 3)

    import tempfile
    import shutil
    from sandbox_agent import (
        setup_sandbox as _setup_v2,
        run_tests_in_sandbox as _run_v2,
        teardown_sandbox as _teardown_v2,
    )
    from sandbox_agent.environments.base import SandboxMode

    sandbox_temp_dir = tempfile.mkdtemp(prefix=f"sandbox_{module}_")
    project_sandbox_dir = os.path.join(sandbox_temp_dir, "project")
    os.makedirs(project_sandbox_dir, exist_ok=True)

    try:
        if code_content:
            parsed_code = parse_code_blocks(code_content)
            if parsed_code:
                for rel_path, content in parsed_code.items():
                    fp = os.path.join(project_sandbox_dir, rel_path.replace("\\", "/"))
                    os.makedirs(os.path.dirname(fp), exist_ok=True)
                    with open(fp, "w", encoding="utf-8") as f:
                        f.write(content)
            else:
                fp = os.path.join(project_sandbox_dir, module, f"{module}.py")
                os.makedirs(os.path.dirname(fp), exist_ok=True)
                with open(fp, "w", encoding="utf-8") as f:
                    f.write(code_content)

        if test_content:
            test_files = parse_code_blocks(test_content)
            if test_files:
                for rel_path, content in test_files.items():
                    fp = os.path.join(project_sandbox_dir, rel_path.replace("\\", "/"))
                    os.makedirs(os.path.dirname(fp), exist_ok=True)
                    with open(fp, "w", encoding="utf-8") as f:
                        f.write(content)
            else:
                test_path = os.path.join(project_sandbox_dir, f"test_{module}.py")
                with open(test_path, "w", encoding="utf-8") as f:
                    f.write(test_content)

        # Check testability before setting up sandbox
        testable, missing_reason = _check_testability(project_sandbox_dir, tech_stack)
        if not testable:
            print(f"      [skip] [{module}] {missing_reason}")
            print(f"      Running LLM logic review instead ...")
            has_issues, issues = _llm_logic_review(state, module, code_content, test_content, tech_stack)
            review_detail = "; ".join(issues[:5]) if issues else "No issues found"
            _log_failure(run_dir, module, "FATAL_MISSING_SETUP",
                         f"{missing_reason}. Test execution skipped. LLM review: {review_detail}",
                         0, "")
            result_status = "FAIL" if has_issues else "PASS"
            print(f"      LLM review result: {result_status} ({len(issues)} issues)")
            test_results[module] = {
                "passed": 0, "failed": 0, "errors": 0,
                "output": f"SKIPPED - {missing_reason}. LLM review: {review_detail}",
                "success": not has_issues,
            }
            shutil.rmtree(sandbox_temp_dir, ignore_errors=True)
            return {
                "test_results": {module: test_results[module]},
                "written_files": written,
                "sandbox_cleanup_paths": [sandbox_temp_dir],
            }

        from sandbox_agent.detector import detect_stack
        stack = detect_stack(project_sandbox_dir, tech_stack)
        smode = SandboxMode(state.get("sandbox_mode", "local"))

        v2_ctx, logs = _setup_v2(project_sandbox_dir, mode=smode,
                                  docker_image=state.get("sandbox_docker_image", None))

        fatal_abort = False
        for attempt in range(max_test_fix_attempts + 1):
            result_data = _run_v2(v2_ctx)
            result = TestResult(**result_data)
            test_results[module] = result_data

            result_status = "PASS" if result.success else "FAIL"
            print(f"      [{result_status}] [{module}] {result.passed} passed, {result.failed} failed, {result.errors} errors (attempt {attempt + 1})")

            if result.success:
                break

            if attempt >= max_test_fix_attempts:
                print(f"      [max] [{module}] Max test fix attempts reached.")
                break

            error_type = _classify_error(result.output)
            if error_type != "FIXABLE":
                print(f"      [fatal] [{module}] Fatal error detected: {error_type}. Skipping fix loop.")
                _log_failure(run_dir, module, error_type,
                             f"Aborted fix loop after attempt {attempt + 1}. Fatal error type: {error_type}",
                             attempt + 1, result.output)
                fatal_abort = True
                break

            print(f"      [fix] [{module}] Fixing tests (attempt {attempt + 1}) ...")

            try:
                llms = _get_llms(state)
                from prompts import test_fixer_prompt
                prompt = test_fixer_prompt()
                response = (prompt | llms["llm"]).invoke({
                    "tech_stack": tech_stack,
                    "module": module,
                    "code": code_content,
                    "tests": test_content,
                    "test_output": result.output,
                })
                fixed_content = response.content or ""
                if fixed_content.strip():
                    parsed_fixed = parse_code_blocks(fixed_content)
                    if parsed_fixed:
                        for rel_path, content in parsed_fixed.items():
                            fp = os.path.join(project_sandbox_dir, rel_path.replace("\\", "/"))
                            os.makedirs(os.path.dirname(fp), exist_ok=True)
                            with open(fp, "w", encoding="utf-8") as f:
                                f.write(content)
                        test_fix_attempts += 1
            except Exception as e:
                print(f"      [error] [{module}] Test fixer failed: {e}")

        if not result.success and not fatal_abort:
            _log_failure(run_dir, module, "FIXABLE_FAILURE",
                         f"Failed after {max_test_fix_attempts + 1} fix attempts",
                         test_fix_attempts, result.output)

        cleanup_paths = [sandbox_temp_dir]
        _teardown_v2(v2_ctx)

    except Exception as e:
        print(f"      [error] [{module}] Sandbox worker error: {e}")
        test_results[module] = {"passed": 0, "failed": 0, "errors": 1, "output": str(e), "success": False}
        _log_failure(run_dir, module, "FATAL_SANDBOX_ERROR", str(e), 0, str(e))
        cleanup_paths = [sandbox_temp_dir]

    # Copy any improved files from the sandbox back into the real project so
    # test fixes actually reach the delivered code, and collect the final
    # code/tests so the graph state reflects what was actually tested.
    final_code = ""
    final_tests = ""
    if os.path.isdir(project_sandbox_dir):
        code_files: dict[str, str] = {}
        test_files: dict[str, str] = {}
        for root, _, files in os.walk(project_sandbox_dir):
            if "venv" in root or "__pycache__" in root:
                continue
            for fname in files:
                src = os.path.join(root, fname)
                rel = os.path.relpath(src, project_sandbox_dir).replace("\\", "/")
                if rel in ("requirements.txt", "pyproject.toml"):
                    continue
                low = rel.lower()
                is_test = (
                    low.startswith("test_") or "/test_" in low
                    or low.startswith("tests/") or "/tests/" in low
                )
                try:
                    with open(src, encoding="utf-8") as fh:
                        content = fh.read()
                except Exception:
                    continue
                if is_test:
                    test_files[rel] = content
                else:
                    code_files[rel] = content
                # Mirror the (possibly fixed) file into the real project
                dst = os.path.join(project_path, rel)
                try:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)
                    written[rel] = "ok"
                except Exception:
                    pass
        final_code = "\n\n".join(
            f"# --- {p} ---\n{c}" for p, c in code_files.items()
        )
        final_tests = "\n\n".join(
            f"# --- {p} ---\n{c}" for p, c in test_files.items()
        )

    fallback_result = {
        "passed": 0, "failed": 0, "errors": 1,
        "output": "Sandbox worker failed", "success": False,
    }
    return {
        "test_results": {module: test_results.get(module, fallback_result)},
        "written_files": written,
        "generated_code": {module: final_code} if final_code else {},
        "tests": {module: final_tests} if final_tests else {},
        "sandbox_cleanup_paths": cleanup_paths,
    }
