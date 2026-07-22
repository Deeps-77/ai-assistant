"""
DevSwarm – Reviewer Agent
Reviews code diffs and workspace files for correctness, style, and security.
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from devswarm.agents.base import REVIEWER_SYSTEM, make_llm
from devswarm.graph.state import PlanTask
from devswarm.tools.file_tools import list_files, read_file


def _extract_json_obj(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {"verdict": "needs_changes", "summary": text, "findings": []}


def run_reviewer(task: PlanTask, workspace: str, coder_summary: str = "") -> dict:
    """
    Run the Reviewer agent over the workspace files for a given task.

    Args:
        task: The PlanTask that was just implemented.
        workspace: Absolute path to the session workspace.
        coder_summary: The Coder agent's summary of changes made.

    Returns:
        dict with keys: verdict, summary, findings
    """
    llm = make_llm(temperature=0.0)

    # Collect workspace file listing
    file_list = list_files.invoke({"workspace": workspace})

    # Read a snapshot of text files (limit to keep context manageable)
    file_contents = {}
    if file_list and file_list != "(empty workspace)":
        paths = [p.strip() for p in file_list.splitlines() if p.strip()]
        for p in paths[:20]:  # cap at 20 files
            ext = p.rsplit(".", 1)[-1] if "." in p else ""
            if ext in ("py", "js", "ts", "go", "java", "md", "toml", "yaml", "yml", "json", "sh"):
                content = read_file.invoke({"workspace": workspace, "path": p})
                file_contents[p] = content[:3000]  # cap per file

    file_section = "\n\n".join(
        f"### {path}\n```\n{content}\n```"
        for path, content in file_contents.items()
    )

    messages = [
        SystemMessage(content=REVIEWER_SYSTEM),
        HumanMessage(
            content=(
                f"Task to review:\n"
                f"Title: {task['title']}\n"
                f"Description: {task['description']}\n"
                f"Acceptance Criteria:\n"
                + "\n".join(f"  - {c}" for c in task["acceptance_criteria"])
                + f"\n\nCoder's change summary:\n{coder_summary}\n\n"
                f"Workspace files:\n{file_section}\n\n"
                "Produce your review as a JSON object."
            )
        ),
    ]

    raw = llm.invoke(messages).content
    result = _extract_json_obj(raw)
    result.setdefault("verdict", "needs_changes")
    result.setdefault("summary", "")
    result.setdefault("findings", [])
    return result
