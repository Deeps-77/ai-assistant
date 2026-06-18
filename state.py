# state.py
from typing import TypedDict, List, Dict, Any, Optional
from pydantic import BaseModel, Field

# --- Pydantic Models for Structured Output ---

class ModuleList(BaseModel):
    """Output from the Planner"""
    stories: List[str] = Field(description="List of user stories derived from requirements")
    modules: List[str] = Field(description="List of backend modules required (e.g., auth, inventory)")

class ArchitectureDoc(BaseModel):
    """Output from the Architect"""
    tech_stack: str = Field(description="Primary tech stack (e.g., FastAPI, PostgreSQL)")
    db_schema: str = Field(description="Database schema definitions")
    api_endpoints: str = Field(description="Key API endpoints design")
    folder_structure: str = Field(description="Project folder structure")

class CodeReview(BaseModel):
    """Output from the Reviewer"""
    score: int = Field(description="Code quality score from 1 to 10")
    issues: List[str] = Field(description="List of issues found")
    logic_correctness: str = Field(description="Brief analysis of logic correctness")
    security_check: str = Field(description="Brief security analysis")

# --- Main Graph State ---

class SoftwareState(TypedDict):
    requirement: str
    stories: List[str]
    architecture: Optional[str]
    modules: List[str]
    
    # Execution Tracking
    pending_modules: List[str]
    completed_modules: List[str]
    current_module: Optional[str]
    
    # Artifacts
    generated_code: Dict[str, str]  # Key: module_name, Value: code_string
    
    # Review Loop
    review_score: Optional[int]
    review_issues: List[str]
    fix_attempts: int