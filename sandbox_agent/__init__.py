import os
import shutil
from typing import Optional

from sandbox_agent.context import SandboxContextV2
from sandbox_agent.detector import detect_stack, SandboxStack
from sandbox_agent.environments.base import SandboxMode
from sandbox_agent.environments.python_env import PythonEnvironment
from sandbox_agent.environments.node_env import NodeEnvironment
from sandbox_agent.environments.rust_env import RustEnvironment
from sandbox_agent.environments.go_env import GoEnvironment
from sandbox_agent.tools.tempdir import create_temp_directory
from sandbox_agent.tools.copier import copy_project_to_sandbox


_ENV_REGISTRY: dict[str, type] = {}


def _register_envs():
    if _ENV_REGISTRY:
        return
    _ENV_REGISTRY["python"] = PythonEnvironment
    _ENV_REGISTRY["node"] = NodeEnvironment
    _ENV_REGISTRY["rust"] = RustEnvironment
    _ENV_REGISTRY["go"] = GoEnvironment


def _get_environment(stack: SandboxStack) -> object:
    _register_envs()
    cls = _ENV_REGISTRY.get(stack.name)
    if cls is None:
        raise RuntimeError(
            f"Unsupported tech stack '{stack.name}'. "
            f"Supported: {list(_ENV_REGISTRY.keys())}"
        )
    return cls()


def setup_sandbox(
    project_path: str,
    mode: SandboxMode = SandboxMode.LOCAL,
    docker_image: Optional[str] = None,
) -> tuple[SandboxContextV2, list[str]]:
    logs: list[str] = []
    temp_dir = create_temp_directory()
    logs.append(f"  Created sandbox at: {temp_dir}")

    stack = detect_stack(project_path)
    logs.append(f"  Detected stack: {stack.name}")

    project_dir = copy_project_to_sandbox(project_path, temp_dir, stack.name)
    logs.append(f"  Copied project to: {project_dir}")

    env = _get_environment(stack)
    env.mode = mode
    if docker_image:
        env.docker_image = docker_image

    context = SandboxContextV2(
        temp_dir=temp_dir,
        project_dir=project_dir,
        stack_name=stack.name,
        env=env,
        mode=mode,
    )

    dep_logs = env.setup(context)
    logs.extend(dep_logs)

    return context, logs


def run_tests_in_sandbox(context: SandboxContextV2) -> dict:
    test_paths = context.env.collect_test_files(context.project_dir)
    if not test_paths:
        return {
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "output": f"No test files found in project ({context.stack_name}).",
            "success": True,
        }
    result = context.env.run_tests(context, test_paths)
    parsed = context.env.parse_output(result.stdout, result.stderr)
    return parsed


def teardown_sandbox(context: SandboxContextV2) -> None:
    try:
        shutil.rmtree(context.temp_dir, ignore_errors=True)
    except Exception as e:
        print(f"  Warning: failed to clean up sandbox: {e}")
