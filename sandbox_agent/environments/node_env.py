import os
import json
from pathlib import Path
from typing import Optional

from sandbox_agent.environments.base import ExecutionEnvironment, SandboxMode, TestRunResult
from sandbox_agent.tools.runner import run_command
from sandbox_agent.tools.parser import parse_jest_output


def _detect_test_script(project_dir: str) -> Optional[str]:
    pkg_path = os.path.join(project_dir, "package.json")
    if not os.path.isfile(pkg_path):
        return None
    try:
        with open(pkg_path, encoding="utf-8") as f:
            pkg = json.load(f)
        scripts = pkg.get("scripts", {})
        for key in ["test", "jest", "mocha", "vitest"]:
            if key in scripts:
                return scripts[key]
        return None
    except (json.JSONDecodeError, OSError):
        return None


class NodeEnvironment(ExecutionEnvironment):
    stack_name = "node"

    def setup(self, context) -> list[str]:
        logs: list[str] = []

        if self.mode == SandboxMode.DOCKER:
            logs.append("  Docker mode: dependencies installed inside container")
            return logs

        logs.append("  Installing npm dependencies...")
        result = run_command(
            mode=SandboxMode.LOCAL,
            cmd=["npm", "install"],
            cwd=context.project_dir,
            timeout=120,
        )
        if result.stderr and "ERR" in result.stderr:
            logs.append(f"  npm install warnings/errors: {result.stderr[-300:]}")
        else:
            logs.append("  npm install completed.")
        return logs

    def collect_test_files(self, project_dir: str) -> list[str]:
        test_paths: list[str] = []
        for pattern in [
            "**/*.test.js", "**/*.test.ts",
            "**/*.spec.js", "**/*.spec.ts",
            "**/__tests__/**/*.js", "**/__tests__/**/*.ts",
        ]:
            for p in Path(project_dir).glob(pattern):
                if p.is_file() and "node_modules" not in str(p):
                    test_paths.append(str(p))
        return test_paths

    def run_tests(self, context, test_paths: list[str]) -> TestRunResult:
        if self.mode == SandboxMode.DOCKER:
            return run_command(
                mode=self.mode,
                cmd=["npx", "jest", "--no-coverage"] + [os.path.relpath(p, context.project_dir).replace("\\", "/") for p in test_paths],
                docker_image=self.docker_image or "node:20-slim",
                mount_dir=context.project_dir,
                timeout=120,
            )

        test_script = _detect_test_script(context.project_dir)
        if test_script:
            cmd = ["npm", "test"]
        else:
            cmd = ["npx", "jest", "--no-coverage"] + [os.path.relpath(p, context.project_dir).replace("\\", "/") for p in test_paths]

        return run_command(
            mode=SandboxMode.LOCAL,
            cmd=cmd,
            cwd=context.project_dir,
            timeout=120,
        )

    def parse_output(self, stdout: str, stderr: str) -> dict:
        return parse_jest_output(stdout, stderr)
