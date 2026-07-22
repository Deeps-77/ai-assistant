"""
DevSwarm Tools – Sandboxed Shell Execution
Runs subprocesses inside the session workspace with strict constraints.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from langchain_core.tools import tool

# Commands that are never allowed, regardless of context
_BLOCKED_PREFIXES = (
    "rm -rf /",
    "sudo",
    "curl",
    "wget",
    "nc ",
    "netcat",
    "ssh",
    "scp",
    "git push",
    "git remote set-url",
)

_TIMEOUT_SECONDS = 60


def _is_blocked(cmd: str) -> bool:
    lower = cmd.strip().lower()
    return any(lower.startswith(b) for b in _BLOCKED_PREFIXES)


@tool
def run_shell(workspace: str, command: str, timeout: int = _TIMEOUT_SECONDS) -> str:
    """
    Run a shell command inside the session workspace sandbox.

    Args:
        workspace: Absolute path to the session workspace (cwd for the command).
        command: Shell command to execute. Blocked commands will be rejected.
        timeout: Max execution time in seconds (default 60).

    Returns:
        Combined stdout + stderr output, or an error/block message.
    """
    if _is_blocked(command):
        return f"[BLOCKED] Command not allowed: {command!r}"

    ws = Path(workspace).resolve()
    if not ws.exists():
        return f"[ERROR] Workspace does not exist: {workspace}"

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = []
        if result.stdout:
            output.append(result.stdout)
        if result.stderr:
            output.append(f"[STDERR]\n{result.stderr}")
        output.append(f"\n[EXIT CODE: {result.returncode}]")
        return "\n".join(output)
    except subprocess.TimeoutExpired:
        return f"[TIMEOUT] Command exceeded {timeout}s: {command!r}"
    except Exception as e:
        return f"[ERROR] {e}"


@tool
def run_tests(workspace: str, test_path: str = ".", extra_args: str = "-v") -> str:
    """
    Run pytest in the session workspace and return the output.

    Args:
        workspace: Absolute path to the session workspace.
        test_path: Relative path to test file or directory (default: ".").
        extra_args: Additional pytest arguments (default: "-v").

    Returns:
        Test output string.
    """
    cmd = f"python -m pytest {test_path} {extra_args} --tb=short --no-header"
    return run_shell.invoke({"workspace": workspace, "command": cmd})


# All shell tools
SHELL_TOOLS = [run_shell, run_tests]
