import os
import shutil


_IGNORE_PATTERNS_BY_STACK: dict[str, list[str]] = {
    "python": [".venv", "__pycache__", "*.pyc", ".git", ".env", "node_modules", ".tox", "build", "dist", "*.egg-info"],
    "node": ["node_modules", ".git", ".env", "dist", "build", "*.log", ".next"],
    "rust": ["target", ".git", ".env"],
    "go": ["bin", ".git", ".env", "*.exe"],
    "java": ["target", ".git", ".env", ".m2", "*.class"],
    "dotnet": ["bin", "obj", ".git", ".env"],
}


def copy_project_to_sandbox(source_path: str, dest_parent: str, stack_name: str) -> str:
    project_dir = os.path.join(dest_parent, "project")
    patterns = _IGNORE_PATTERNS_BY_STACK.get(stack_name, [".venv", "__pycache__", "*.pyc", ".git", ".env", "node_modules"])
    shutil.copytree(
        source_path,
        project_dir,
        ignore=shutil.ignore_patterns(*patterns),
    )
    return project_dir
