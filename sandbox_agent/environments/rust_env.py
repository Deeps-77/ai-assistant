from sandbox_agent.environments.base import ExecutionEnvironment, SandboxMode, TestRunResult
from sandbox_agent.tools.runner import run_command
from sandbox_agent.tools.parser import parse_cargo_output


class RustEnvironment(ExecutionEnvironment):
    stack_name = "rust"

    def setup(self, context) -> list[str]:
        logs: list[str] = []

        if self.mode == SandboxMode.DOCKER:
            logs.append("  Docker mode: dependencies built inside container")
            return logs

        logs.append("  Building project and fetching dependencies...")
        result = run_command(
            mode=SandboxMode.LOCAL,
            cmd=["cargo", "build"],
            cwd=context.project_dir,
            timeout=300,
        )
        if result.stderr and "error" in result.stderr.lower():
            logs.append(f"  cargo build errors: {result.stderr[-500:]}")
        else:
            logs.append("  cargo build completed.")
        return logs

    def collect_test_files(self, project_dir: str) -> list[str]:
        return []

    def run_tests(self, context, test_paths: list[str]) -> TestRunResult:
        return run_command(
            mode=self.mode,
            cmd=["cargo", "test"],
            cwd=context.project_dir,
            timeout=300,
            docker_image=self.docker_image or "rust:1.77-slim",
            mount_dir=context.project_dir,
        )

    def parse_output(self, stdout: str, stderr: str) -> dict:
        parsed = parse_cargo_output(stdout, stderr)
        if not parsed["output"]:
            parsed["output"] = stdout[-3000:] + "\n" + stderr[-2000:]
        return parsed
