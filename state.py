import operator
from typing import TypedDict, List, Dict, Optional, Any, Annotated
from pydantic import BaseModel, Field


class ModuleList(BaseModel):
    stories: List[str] = Field(description="User stories derived from requirements")
    modules: List[str] = Field(description="Backend module names (e.g., auth, users, inventory)")
    tech_stack: str = Field(default="", description="Detected or specified tech stack")


class ArchitectureDoc(BaseModel):
    tech_stack: str = Field(description="Primary tech stack")
    db_schema: str = Field(description="Database schema definitions")
    api_endpoints: str = Field(description="Key API endpoint designs")
    folder_structure: str = Field(description="Project folder structure as a multi-line tree")
    architecture_diagram: str = Field(description="Text-based architecture diagram")


class ModuleFile(BaseModel):
    path: str = Field(description="File path relative to project root")
    purpose: str = Field(description="What this file contains")
    exports: List[str] = Field(description="Key classes, functions, or variables defined here")


class ModulePlan(BaseModel):
    module_name: str = Field(description="Name of the module")
    files: List[ModuleFile] = Field(description="Files to create for this module")
    dependencies: List[str] = Field(description="Other modules this module depends on")
    api_routes: List[str] = Field(description="API endpoints this module exposes")


class CodeReview(BaseModel):
    score: int = Field(description="Code quality score from 1 to 10")
    issues: List[str] = Field(description="List of issues found")
    logic_correctness: str = Field(description="Brief logic correctness analysis")
    security_check: str = Field(description="Brief security analysis")


class TestResult(BaseModel):
    passed: int = Field(default=0, description="Number of passed tests")
    failed: int = Field(default=0, description="Number of failed tests")
    errors: int = Field(default=0, description="Number of errors")
    output: str = Field(default="", description="Full pytest output")
    success: bool = Field(default=False, description="Whether all tests passed")


class ExecutionPlan(BaseModel):
    """Structured plan produced by the supervisor agent.

    Decides the delivery graph flow per-prompt instead of the rigid
    fixed pipeline. Consumed by routing functions in :mod:`graph`.
    """

    pause_for_plan_approval: bool = Field(
        default=False,
        description="Pause after planning to show the plan for approval before building.",
    )
    skip_build: bool = Field(
        default=False,
        description="Plan-only request: do not generate code after approval.",
    )
    skip_tests: bool = Field(
        default=False,
        description="Skip the QA / test stage entirely.",
    )
    execution_mode: str = Field(
        default="parallel", description="'parallel' or 'sequential'"
    )
    review_threshold: int = Field(
        default=7, description="Minimum review score to pass (1-10)", ge=1, le=10
    )
    max_fix_attempts: int = Field(
        default=3, description="Max review-fix cycles per module", ge=1
    )
    security_focus: bool = Field(
        default=False, description="Emphasize security review."
    )
    notes: str = Field(default="", description="Short rationale for the chosen flow")


class ProjectAnalysis(BaseModel):
    tech_stack: str = Field(description="Detected tech stack")
    modules: List[str] = Field(description="Existing module names found")
    missing_modules: List[str] = Field(description="Modules that should exist but don't")
    issues: List[str] = Field(description="Quality/security issues found")
    architecture_summary: str = Field(description="Summary of existing project architecture")


# Reducer helpers for safe parallel merging

def _merge_dicts(a: Dict[str, str], b: Dict[str, str]) -> Dict[str, str]:
    return {**a, **b}


def _append_list(a: List[str], b: List[str]) -> List[str]:
    seen = set(a)
    return a + [x for x in b if x not in seen]


def _append_int_list(a: List[int], b: List[int]) -> List[int]:
    return a + b


def _max_int(a: int, b: int) -> int:
    return max(a, b)


def _max_score(a: Optional[int], b: Optional[int]) -> Optional[int]:
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


# Per-worker state for the parallel execution subgraph

class WorkerState(TypedDict):
    module_name: str
    requirement: str
    architecture: str
    stories: List[str]
    quality_guide: Optional[str]
    tech_stack: str
    project_path: str
    provider: str
    llm_base_url: str
    llm_model: str
    max_retries: int
    module_plan: Optional[str]
    generated_code: Dict[str, str]
    tests: Dict[str, str]

    review_score: Optional[int]
    review_issues: List[str]
    fix_attempts: int
    score_history: List[int]
    max_fix_attempts: int
    review_threshold: int

    human_approved: bool
    human_feedback: str

    completed_modules: List[str]


# Per-module sandbox worker state

class SandboxWorkerState(TypedDict):
    module_name: str
    project_path: str
    tech_stack: str
    output_dir: str
    run_dir: str
    generated_code: Dict[str, str]
    tests: Dict[str, str]
    sandbox_enabled: bool
    sandbox_mode: str
    sandbox_docker_image: Optional[str]
    provider: str
    llm_base_url: str
    llm_model: str
    sandbox_stack: Optional[str]
    sandbox_path: Optional[str]
    test_results: Dict[str, Any]
    test_fix_attempts: int
    max_test_fix_attempts: int
    written_files: Dict[str, str]
    sandbox_cleanup_paths: List[str]


class SoftwareState(TypedDict):
    requirement: str

    mode: str                                # "create_new" | "analyze" | "update"
    plan_mode: bool                           # opencode-style: pause for plan approval before building
    tech_stack: Optional[str]                # e.g. "Python/FastAPI", "Rust/Axum", or None
    project_path: Optional[str]              # Target project directory on disk
    output_dir: str                          # Base output directory
    execution_plan: Optional[dict]           # ExecutionPlan produced by the supervisor agent
    run_dir: str                             # Per-run output directory with timestamp
    max_fix_attempts: int
    review_threshold: int                    # Configurable, default 7
    adaptive_threshold: bool                 # Auto-lower threshold if score is stuck
    execution_mode: str                      # "parallel" | "sequential"
    max_concurrent_modules: int

    provider: str                            # "ollama" | "lm_studio"
    llm_base_url: str                        # API endpoint URL
    llm_model: str                           # Model identifier
    ctx_size: Optional[int]                  # Ollama only: context window (num_ctx)
    max_retries: int                         # Max retries on transient LLM failures

    stories: List[str]
    architecture: Optional[str]
    modules: List[str]
    quality_guide: Optional[str]

    analysis: Optional[ProjectAnalysis]  # Structured result of `analyze` mode

    pending_modules: List[str]
    completed_modules: Annotated[List[str], _append_list]
    batch_modules: List[str]  # Current parallel batch being dispatched
    current_module: Optional[str]
    module_plan: Optional[str]

    generated_code: Annotated[Dict[str, str], operator.or_]
    tests: Annotated[Dict[str, str], operator.or_]

    review_score: Annotated[Optional[int], _max_score]
    review_issues: Annotated[List[str], _append_list]
    fix_attempts: Annotated[int, _max_int]
    score_history: Annotated[List[int], _append_int_list]

    human_approved: bool
    human_feedback: str

    # Supervisor-decided flow controls (set by supervisor_node)
    skip_tests: bool                          # skip the QA / test stage
    security_focus: bool                      # emphasize security review
    plan_approved: bool                      # plan_review interrupt outcome
    plan_rejected: bool                      # plan_review rejected -> regenerate
    plan_reviews_completed: Annotated[int, operator.add]  # count of resolved plan_review gates

    existing_structure: Optional[str]        # Tree string for analyze/update modes
    existing_code: Dict[str, str]            # rel_path -> content for existing project
    written_files: Annotated[Dict[str, str], operator.or_]

    delivery_package: Optional[str]

    sandbox_enabled: bool
    sandbox_path: Optional[str]
    sandbox_mode: str                        # "local" | "docker"
    sandbox_docker_image: Optional[str]      # Override Docker image
    sandbox_stack: Optional[str]             # Detected stack name
    test_results: Annotated[Dict[str, Any], operator.or_]  # module_name -> TestResult dict
    test_fix_attempts: Annotated[int, _max_int]
    max_test_fix_attempts: int
    sandbox_cleanup_paths: Annotated[List[str], _append_list]
