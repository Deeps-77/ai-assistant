from typing import TypedDict, List, Dict, Optional
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


class ProjectAnalysis(BaseModel):
    tech_stack: str = Field(description="Detected tech stack")
    modules: List[str] = Field(description="Existing module names found")
    missing_modules: List[str] = Field(description="Modules that should exist but don't")
    issues: List[str] = Field(description="Quality/security issues found")
    architecture_summary: str = Field(description="Summary of existing project architecture")


class SoftwareState(TypedDict):
    requirement: str

    mode: str                                # "create_new" | "analyze" | "update"
    tech_stack: str                          # e.g. "Python/FastAPI", "Rust/Axum"
    project_path: Optional[str]              # Target project directory on disk
    output_dir: str                          # Base output directory
    max_fix_attempts: int
    review_threshold: int                    # Configurable, default 7

    provider: str                            # "ollama" | "lm_studio"
    llm_base_url: str                        # API endpoint URL
    llm_model: str                           # Model identifier

    stories: List[str]
    architecture: Optional[str]
    modules: List[str]
    quality_guide: Optional[str]

    pending_modules: List[str]
    completed_modules: List[str]
    current_module: Optional[str]
    module_plan: Optional[str]

    generated_code: Dict[str, str]
    tests: Dict[str, str]

    review_score: Optional[int]
    review_issues: List[str]
    fix_attempts: int

    existing_structure: Optional[str]        # Tree string for analyze/update modes
    existing_code: Dict[str, str]            # rel_path -> content for existing project
    written_files: Dict[str, str]            # rel_path -> "ok" | "error: ..."

    delivery_package: Optional[str]
