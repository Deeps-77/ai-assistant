import os
import subprocess
from typing import Optional

from sandbox_agent.environments.base import SandboxMode, TestRunResult


def run_local(
    cmd: list[str],
    cwd: str = "",
    timeout: int = 120,
    env_vars: Optional[dict[str, str]] = None,
) -> TestRunResult:
    env = os.environ.copy()
    if env_vars:
        env.update(env_vars)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd or None,
            env=env,
        )
        return TestRunResult(stdout=result.stdout, stderr=result.stderr)
    except subprocess.TimeoutExpired:
        return TestRunResult(
            stdout="",
            stderr=f"Command timed out after {timeout}s: {' '.join(cmd)}",
        )


def run_docker(
    image: str,
    cmd: list[str],
    mount_dir: str = "",
    container_mount: str = "/project",
    timeout: int = 120,
) -> TestRunResult:
    docker_cmd = [
        "docker", "run", "--rm",
        "-v", f"{mount_dir}:{container_mount}",
        "-w", container_mount,
        image,
    ] + cmd
    return run_local(docker_cmd, timeout=timeout)


def run_command(
    mode: SandboxMode,
    cmd: list[str],
    cwd: str = "",
    timeout: int = 120,
    docker_image: str = "",
    mount_dir: str = "",
) -> TestRunResult:
    if mode == SandboxMode.DOCKER:
        return run_docker(
            image=docker_image,
            cmd=cmd,
            mount_dir=mount_dir,
            timeout=timeout,
        )
    return run_local(cmd=cmd, cwd=cwd, timeout=timeout)
