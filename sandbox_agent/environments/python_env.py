import os
import sys
import subprocess
from pathlib import Path

from sandbox_agent.environments.base import ExecutionEnvironment, SandboxMode, TestRunResult
from sandbox_agent.tools.runner import run_command
from sandbox_agent.tools.parser import parse_pytest_output


class PythonEnvironment(ExecutionEnvironment):
    stack_name = "python"

    def setup(self, context) -> list[str]:
        logs: list[str] = []
        venv_dir = os.path.join(context.temp_dir, ".venv")

        python_exe = sys.executable
        logs.append(f"  Creating virtual environment...")
        result = subprocess.run(
            [python_exe, "-m", "venv", venv_dir],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            logs.append(f"  venv creation failed: {result.stderr[-300:]}")
            raise RuntimeError(f"Failed to create venv: {result.stderr}")

        if os.name == "nt":
            venv_python = os.path.join(venv_dir, "Scripts", "python.exe")
            venv_pip = os.path.join(venv_dir, "Scripts", "pip.exe")
        else:
            venv_python = os.path.join(venv_dir, "bin", "python")
            venv_pip = os.path.join(venv_dir, "bin", "pip")

        context.extra["venv_python"] = venv_python
        context.extra["venv_pip"] = venv_pip

        if not os.path.isfile(venv_python):
            logs.append(f"  venv python not found at {venv_python}")
            raise RuntimeError(f"venv python not found at {venv_python}")

        requirements = os.path.join(context.project_dir, "requirements.txt")
        pyproject = os.path.join(context.project_dir, "pyproject.toml")

        if os.path.isfile(requirements):
            logs.append(f"  Installing from requirements.txt...")
            r = subprocess.run(
                [venv_pip, "install", "-r", requirements],
                capture_output=True, text=True, timeout=120,
            )
            logs.append(r.stdout[-500:] if r.stdout else "")
            if r.returncode != 0:
                logs.append(f"  pip install (requirements) failed: {r.stderr[-300:]}")
        elif os.path.isfile(pyproject):
            logs.append(f"  Installing from pyproject.toml...")
            r = subprocess.run(
                [venv_pip, "install", "-e", context.project_dir],
                capture_output=True, text=True, timeout=120,
            )
            logs.append(r.stdout[-500:] if r.stdout else "")
            if r.returncode != 0:
                logs.append(f"  pip install (pyproject) failed: {r.stderr[-300:]}")
        else:
            logs.append("  No dependencies to install.")

        r = subprocess.run(
            [venv_pip, "install", "pytest"],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            logs.append(f"  pip install pytest failed: {r.stderr[-200:]}")
        else:
            logs.append("  pytest installed.")

        return logs

    def collect_test_files(self, project_dir: str) -> list[str]:
        test_paths: list[str] = []
        for pattern in ["**/test_*.py", "**/*_test.py", "**/tests/**/*.py"]:
            for p in Path(project_dir).glob(pattern):
                if p.is_file() and "venv" not in str(p) and "__pycache__" not in str(p):
                    test_paths.append(str(p))
        return test_paths

    def run_tests(self, context, test_paths: list[str]) -> TestRunResult:
        if self.mode == SandboxMode.DOCKER:
            return run_command(
                mode=self.mode,
                cmd=["pytest", "-v"] + [p.replace("\\", "/") for p in test_paths],
                docker_image=self.docker_image or "python:3.12-slim",
                mount_dir=context.project_dir,
                timeout=120,
            )

        python_exe = context.extra.get("venv_python", sys.executable)
        cmd = [python_exe, "-m", "pytest", *test_paths, "-v"]
        return run_command(
            mode=SandboxMode.LOCAL,
            cmd=cmd,
            cwd=context.project_dir,
            timeout=120,
        )

    def parse_output(self, stdout: str, stderr: str) -> dict:
        return parse_pytest_output(stdout, stderr)
