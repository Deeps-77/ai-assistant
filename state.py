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
    module_plan: Optional[str]
    generated_code: Dict[str, str]
    tests: Dict[str, str]

    review_score: Optional[int]
    review_issues: List[str]
    fix_attempts: int
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
    tech_stack: Optional[str]                # e.g. "Python/FastAPI", "Rust/Axum", or None
    project_path: Optional[str]              # Target project directory on disk
    output_dir: str                          # Base output directory
    run_dir: str                             # Per-run output directory with timestamp
    max_fix_attempts: int
    review_threshold: int                    # Configurable, default 7
    execution_mode: str                      # "parallel" | "sequential"
    max_concurrent_modules: int

    provider: str                            # "ollama" | "lm_studio"
    llm_base_url: str                        # API endpoint URL
    llm_model: str                           # Model identifier

    stories: List[str]
    architecture: Optional[str]
    modules: List[str]
    quality_guide: Optional[str]

    pending_modules: List[str]
    completed_modules: Annotated[List[str], _append_list]
    batch_modules: List[str]                   # Current parallel batch being dispatched
    current_module: Optional[str]
    module_plan: Optional[str]

    generated_code: Annotated[Dict[str, str], operator.or_]
    tests: Annotated[Dict[str, str], operator.or_]

    review_score: Optional[int]
    review_issues: List[str]
    fix_attempts: int

    human_approved: bool
    human_feedback: str

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
    test_fix_attempts: int
    max_test_fix_attempts: int
    sandbox_cleanup_paths: Annotated[List[str], _append_list]
