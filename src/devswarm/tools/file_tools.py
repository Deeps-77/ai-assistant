"""
DevSwarm Tools – File Operations
All file tools operate strictly within the session workspace.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool


def _safe_path(workspace: str, relative: str) -> Path:
    """Resolve a relative path within the workspace and guard against traversal."""
    ws = Path(workspace).resolve()
    target = (ws / relative).resolve()
    if not str(target).startswith(str(ws)):
        raise ValueError(f"Path traversal attempt blocked: {relative!r}")
    return target


@tool
def read_file(workspace: str, path: str) -> str:
    """
    Read a file from the session workspace.

    Args:
        workspace: Absolute path to the session workspace directory.
        path: Relative path to the file within the workspace.

    Returns:
        File contents as a string, or an error message.
    """
    try:
        target = _safe_path(workspace, path)
        if not target.exists():
            return f"[ERROR] File not found: {path}"
        return target.read_text(encoding="utf-8")
    except Exception as e:
        return f"[ERROR] {e}"


@tool
def write_file(workspace: str, path: str, content: str) -> str:
    """
    Write content to a file in the session workspace (creates dirs as needed).

    Args:
        workspace: Absolute path to the session workspace directory.
        path: Relative path to the file within the workspace.
        content: Full content to write.

    Returns:
        Success confirmation or error message.
    """
    try:
        target = _safe_path(workspace, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"[OK] Written {len(content)} chars to {path}"
    except Exception as e:
        return f"[ERROR] {e}"


@tool
def delete_file(workspace: str, path: str) -> str:
    """
    Delete a file from the session workspace.

    Args:
        workspace: Absolute path to the session workspace directory.
        path: Relative path to the file within the workspace.

    Returns:
        Success confirmation or error message.
    """
    try:
        target = _safe_path(workspace, path)
        if not target.exists():
            return f"[WARN] File not found, nothing deleted: {path}"
        target.unlink()
        return f"[OK] Deleted {path}"
    except Exception as e:
        return f"[ERROR] {e}"


@tool
def list_files(workspace: str, subdir: Optional[str] = None) -> str:
    """
    List all files in the workspace (or a subdirectory).

    Args:
        workspace: Absolute path to the session workspace directory.
        subdir: Optional relative subdirectory to list.

    Returns:
        Newline-separated list of relative file paths.
    """
    try:
        base = _safe_path(workspace, subdir or ".")
        if not base.exists():
            return f"[WARN] Directory not found: {subdir}"
        files = []
        for f in sorted(base.rglob("*")):
            if f.is_file():
                files.append(str(f.relative_to(Path(workspace).resolve())))
        return "\n".join(files) if files else "(empty workspace)"
    except Exception as e:
        return f"[ERROR] {e}"


@tool
def diff_files(workspace: str, path: str, new_content: str) -> str:
    """
    Show a unified diff between the current file content and proposed new content.

    Args:
        workspace: Absolute path to the session workspace directory.
        path: Relative path to the file.
        new_content: The proposed new content.

    Returns:
        Unified diff string.
    """
    import difflib

    try:
        target = _safe_path(workspace, path)
        old_content = target.read_text(encoding="utf-8") if target.exists() else ""
        diff = difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
        result = "".join(diff)
        return result if result else "(no changes)"
    except Exception as e:
        return f"[ERROR] {e}"


# Convenience: all file tools as a list for agent binding
FILE_TOOLS = [read_file, write_file, delete_file, list_files, diff_files]
