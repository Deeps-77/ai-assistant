from dataclasses import dataclass, field
from typing import Any, Optional
from sandbox_agent.environments.base import SandboxMode


@dataclass
class SandboxStack:
    name: str
    test_cmd: list[str]
    dep_cmd: list[str]
    test_file_patterns: list[str]
    docker_default_image: str = ""


@dataclass
class SandboxContextV2:
    temp_dir: str
    project_dir: str
    stack_name: str
    env: Any
    mode: SandboxMode = SandboxMode.LOCAL
    docker_image: Optional[str] = None
    extra: dict = field(default_factory=dict)
