import os
from dataclasses import dataclass
from typing import Optional

from sandbox_agent import (
    setup_sandbox as _agent_setup,
    run_tests_in_sandbox as _agent_run_tests,
    teardown_sandbox as _agent_teardown,
)
from sandbox_agent.context import SandboxContextV2
from sandbox_agent.environments.base import SandboxMode


@dataclass
class SandboxContext:
    venv_dir: str
    project_dir: str
    python_exe: str
    pip_exe: str
    temp_dir: str


def _from_v2(v2: SandboxContextV2) -> SandboxContext:
    return SandboxContext(
        venv_dir=os.path.join(v2.temp_dir, ".venv"),
        project_dir=v2.project_dir,
        python_exe=v2.extra.get("venv_python", ""),
        pip_exe=v2.extra.get("venv_pip", ""),
        temp_dir=v2.temp_dir,
    )


def setup_sandbox(
    project_path: str,
    mode: str = "local",
    docker_image: Optional[str] = None,
) -> tuple[SandboxContext, list[str]]:
    smode = SandboxMode(mode) if isinstance(mode, str) else mode
    v2_ctx, logs = _agent_setup(project_path, mode=smode, docker_image=docker_image)
    ctx = _from_v2(v2_ctx)
    return ctx, logs


def run_tests_in_sandbox(context: SandboxContext) -> dict:
    v2_ctx = SandboxContextV2(
        temp_dir=context.temp_dir,
        project_dir=context.project_dir,
        stack_name="python",
        env=None,
    )
    v2_ctx.extra["venv_python"] = context.python_exe
    v2_ctx.extra["venv_pip"] = context.pip_exe
    return _agent_run_tests(v2_ctx)


def run_tests_in_sandbox_v2(context: SandboxContextV2) -> dict:
    return _agent_run_tests(context)


def teardown_sandbox(context: SandboxContext) -> None:
    _agent_teardown(
        SandboxContextV2(
            temp_dir=context.temp_dir,
            project_dir=context.project_dir,
            stack_name="python",
            env=None,
        )
    )
