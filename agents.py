import os
import json
from typing import Any
from langchain_core.exceptions import OutputParserException
from dotenv import load_dotenv

from state import (
    SoftwareState,
    ModuleList,
    ArchitectureDoc,
    ModulePlan,
    ModuleFile,
    CodeReview,
    ProjectAnalysis,
)
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
    analyze_project_prompt,
)
from file_tools import (
    extract_folder_structure_from_architecture,
    init_project_structure,
    ensure_directory,
    write_module_files,
    write_test_files,
    read_project_structure,
    read_project_files,
    parse_code_blocks,
)

load_dotenv()

_llm_cache: dict = {}


def _get_llms(state: SoftwareState) -> dict[str, Any]:
    provider = state.get("provider", "ollama")
    base_url = state.get("llm_base_url", "https://ollama.com")
    model = state.get("llm_model", "gemma3:12b-cloud")
    cache_key = f"{provider}:{base_url}:{model}"

    if cache_key in _llm_cache:
        return _llm_cache[cache_key]

    if provider == "lm_studio":
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(base_url=base_url, api_key="lm-studio",
                         model=model, temperature=0)
        method = "json_schema"
    else:
        from langchain_ollama import ChatOllama
        llm = ChatOllama(base_url=base_url, model=model, temperature=0)
        method = "json_mode"

    result = {
        "llm": llm,
        "planner": llm.with_structured_output(ModuleList, method=method),
        "architect": llm.with_structured_output(ArchitectureDoc, method=method),
        "module_planner": llm.with_structured_output(ModulePlan, method=method),
        "reviewer": llm.with_structured_output(CodeReview, method=method),
        "analyzer": llm.with_structured_output(ProjectAnalysis, method=method),
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
        result: ModuleList = chain.invoke({"requirement": state["requirement"]})
    except OutputParserException:
        print("   Planner JSON parse failed; attempting fallback...")
        raw_response = llms["llm"].invoke(
            planner_fallback_prompt().format(requirement=state["requirement"])
        )
        try:
            raw_dict = json.loads(raw_response.content)
        except json.JSONDecodeError:
            print("   Planner fallback also failed; using safe defaults.")
            return {
                "stories": [f"Implement {state['requirement']}"],
                "modules": ["app"],
                "tech_stack": state.get("tech_stack", "Python/FastAPI"),
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
    tech_stack = state.get("tech_stack", "Python/FastAPI")
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
    except OutputParserException:
        print("   Architect JSON parse failed; attempting fallback...")
        raw_response = llms["llm"].invoke(
            architect_fallback_prompt().format(
                tech_stack=tech_stack,
                stories=state["stories"],
                modules=state["modules"],
            )
        )
        try:
            raw_dict = json.loads(raw_response.content)
        except json.JSONDecodeError:
            print("   Architect fallback also failed; using safe defaults.")
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
    tech_stack = state.get("tech_stack", "Python/FastAPI")
    print(f"--- QUALITY: Generating quality guide for {tech_stack} ---")
    llms = _get_llms(state)

    chain = quality_guide_prompt() | llms["llm"]
    response = chain.invoke({"tech_stack": tech_stack})

    guide = response.content or ""
    if not guide.strip():
        guide = f"# Quality Guide for {tech_stack}\n- Follow best practices for {tech_stack}\n"
        print("   Quality guide empty; using fallback.")

    print(f"   Quality guide generated ({len(guide)} chars)")
    return {"quality_guide": guide}


# ═══════════════════════════════════════════════
# NODE 2c — PROJECT INIT
# ═══════════════════════════════════════════════


def project_init_node(state: SoftwareState):
    project_path = state.get("project_path") or os.path.join(
        state.get("output_dir", "outputs"), "project"
    )
    tech_stack = state.get("tech_stack", "Python/FastAPI")
    print(f"--- INIT: Creating project skeleton at {project_path} ---")

    folder_structure = extract_folder_structure_from_architecture(
        state.get("architecture", "")
    )

    if folder_structure:
        print("   Creating directory structure from architecture...")
        init_project_structure(project_path, folder_structure)
    else:
        print("   No folder structure in architecture; creating minimal directories.")
        ensure_directory(project_path)

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
    tech_stack = state.get("tech_stack", "Python/FastAPI")
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
    except OutputParserException:
        print("   Module planner JSON parse failed; attempting fallback...")
        raw_response = llms["llm"].invoke(
            module_planner_fallback_prompt().format(module=module, architecture=state.get("architecture", ""))
        )
        try:
            raw_dict = json.loads(raw_response.content)
        except json.JSONDecodeError:
            print("   Module planner fallback also failed; using empty plan.")
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


def module_coder_node(state: SoftwareState):
    module = state["current_module"]
    tech_stack = state.get("tech_stack", "Python/FastAPI")
    print(f"--- MODULE CODER: Coding [{module}] ({tech_stack}) ---")
    llms = _get_llms(state)

    module_plan = state.get("module_plan", "")
    planned_paths = _extract_paths_from_plan(module_plan)
    exact_file_paths = "\n".join(f"  - {p}" for p in planned_paths) if planned_paths else module_plan

    prompt = module_coder_prompt()
    chain = prompt | llms["llm"]
    response = chain.invoke({
        "tech_stack": tech_stack,
        "module": module,
        "architecture": state["architecture"],
        "exact_file_paths": exact_file_paths,
        "quality_guide": state.get("quality_guide", ""),
    })

    content = response.content or ""
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


# ═══════════════════════════════════════════════
# NODE 5 — REVIEWER
# ═══════════════════════════════════════════════


def reviewer_node(state: SoftwareState):
    module = state["current_module"]
    code = state["generated_code"].get(module, "")
    tech_stack = state.get("tech_stack", "Python/FastAPI")
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
        })
    except OutputParserException:
        print("   Review JSON parse failed; attempting fallback...")
        raw_response = llms["llm"].invoke(
            reviewer_fallback_prompt().format(tech_stack=tech_stack, module=module, code=code)
        )
        try:
            raw_dict = json.loads(raw_response.content)
        except json.JSONDecodeError:
            print("   Review fallback also failed; using safe defaults.")
            raw_dict = {}
        review = _flatten_review(raw_dict)

    print(f"   Score: {review.score}/10 | Issues: {len(review.issues)}")
    for issue in review.issues:
        print(f"     * {issue}")

    return {
        "review_score": review.score,
        "review_issues": review.issues,
    }


# ═══════════════════════════════════════════════
# NODE 6 — FIXER
# ═══════════════════════════════════════════════


def fixer_node(state: SoftwareState):
    module = state["current_module"]
    code = state["generated_code"].get(module, "")
    issues = state.get("review_issues", [])
    attempts = state.get("fix_attempts", 0) + 1
    tech_stack = state.get("tech_stack", "Python/FastAPI")

    print(f"--- FIXER: Fixing [{module}] (attempt {attempts}) ({tech_stack}) ---")
    llms = _get_llms(state)

    quality = state.get("quality_guide", "")

    prompt = fixer_prompt()
    chain = prompt | llms["llm"]
    response = chain.invoke({
        "tech_stack": tech_stack,
        "module": module,
        "code": code,
        "issues": "\n".join(f"- {i}" for i in issues),
        "quality_guide": quality,
    })

    code_map = dict(state["generated_code"])
    code_map[module] = response.content

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
    }


# ═══════════════════════════════════════════════
# NODE 8 — QA AGENT
# ═══════════════════════════════════════════════


def qa_node(state: SoftwareState):
    tech_stack = state.get("tech_stack", "Python/FastAPI")
    print(f"--- QA AGENT: Generating Tests ({tech_stack}) ---")
    llms = _get_llms(state)

    tests: dict[str, str] = {}

    for module, code in state["generated_code"].items():
        print(f"   Generating tests for [{module}]...")

        prompt = qa_prompt()
        chain = prompt | llms["llm"]
        response = chain.invoke({
            "tech_stack": tech_stack,
            "module": module,
            "code": code,
        })
        tests[module] = response.content

    print(f"   Tests generated for {len(tests)} modules.")
    return {"tests": tests}


# ═══════════════════════════════════════════════
# NODE 8b — FILE WRITER
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

    tech_stack = state.get("tech_stack", "Python/FastAPI")

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
    except OutputParserException:
        print("   Analyzer parse failed; returning minimal analysis.")
        return {
            "tech_stack": state.get("tech_stack", "Unknown"),
            "modules": list(existing_files.keys()),
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
        "stories": stories or state.get("stories", []),
        "pending_modules": analysis.missing_modules or analysis.modules,
        "quality_guide": None,
    }
