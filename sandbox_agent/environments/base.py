from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional


class SandboxMode(str, Enum):
    LOCAL = "local"
    DOCKER = "docker"


class TestRunResult:
    def __init__(self, stdout: str = "", stderr: str = ""):
        self.stdout = stdout
        self.stderr = stderr


class ExecutionEnvironment(ABC):
    stack_name: str = ""
    mode: SandboxMode = SandboxMode.LOCAL
    docker_image: str = ""

    @abstractmethod
    def setup(self, context: object) -> list[str]:
        ...

    @abstractmethod
    def collect_test_files(self, project_dir: str) -> list[str]:
        ...

    @abstractmethod
    def run_tests(self, context: object, test_paths: list[str]) -> TestRunResult:
        ...

    @abstractmethod
    def parse_output(self, stdout: str, stderr: str) -> dict:
        ...
