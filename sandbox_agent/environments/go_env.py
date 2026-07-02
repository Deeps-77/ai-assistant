from pathlib import Path

from sandbox_agent.environments.base import ExecutionEnvironment, SandboxMode, TestRunResult
from sandbox_agent.tools.runner import run_command
from sandbox_agent.tools.parser import parse_go_output


class GoEnvironment(ExecutionEnvironment):
    stack_name = "go"

    def setup(self, context) -> list[str]:
        logs: list[str] = []

        if self.mode == SandboxMode.DOCKER:
            logs.append("  Docker mode: dependencies downloaded inside container")
            return logs

        logs.append("  Downloading Go dependencies...")
        result = run_command(
            mode=SandboxMode.LOCAL,
            cmd=["go", "mod", "download"],
            cwd=context.project_dir,
            timeout=120,
        )
        if result.stderr and "error" in result.stderr.lower():
            logs.append(f"  go mod download errors: {result.stderr[-300:]}")
        else:
            logs.append("  go mod download completed.")
        return logs

    def collect_test_files(self, project_dir: str) -> list[str]:
        test_files: list[str] = []
        for p in Path(project_dir).rglob("*_test.go"):
            if p.is_file() and "vendor" not in str(p):
                test_files.append(str(p))
        return test_files

    def run_tests(self, context, test_paths: list[str]) -> TestRunResult:
        return run_command(
            mode=self.mode,
            cmd=["go", "test", "./..."],
            cwd=context.project_dir,
            timeout=180,
            docker_image=self.docker_image or "golang:1.22",
            mount_dir=context.project_dir,
        )

    def parse_output(self, stdout: str, stderr: str) -> dict:
        parsed = parse_go_output(stdout, stderr)
        if not parsed["output"]:
            parsed["output"] = stdout[-3000:] + "\n" + stderr[-2000:]
        return parsed
