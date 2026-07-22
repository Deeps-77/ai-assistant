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
    all_paths: list[str] = []
    if file_list and file_list != "(empty workspace)":
        all_paths = [p.strip() for p in file_list.splitlines() if p.strip()]

    TEXT_EXTS = {
        "py", "pyi", "pyx", "pxd",          # Python
        "js", "jsx", "mjs", "cjs",           # JavaScript
        "ts", "tsx", "mts", "cts",           # TypeScript
        "go", "java", "rs", "rb", "php",     # Backend languages
        "c", "cpp", "cc", "cxx", "h", "hpp", "hxx",  # C/C++
        "cs", "fs", "swift", "kt", "scala",  # Other compiled
        "sql", "graphql", "prisma", "mig",   # Data/query
        "html", "htm", "xhtml", "css", "scss", "sass", "less",  # Web
        "xml", "json", "yaml", "yml", "toml", "ini", "cfg", "conf",  # Config
        "md", "rst", "txt", "log",           # Docs
        "sh", "bash", "zsh", "ps1", "bat", "cmd",  # Shell
        "env", "gitignore", "dockerfile", "makefile", "procfile",  # DevOps
        "lock", "gradle", "sbt", "cmake",    # Build
        "svg", "tex", "bib",                 # Misc text
    }

    for p in all_paths[:30]:  # cap at 30 files
        ext = p.rsplit(".", 1)[-1].lower() if "." in p else ""
        if ext in TEXT_EXTS:
            content = read_file.invoke({"workspace": workspace, "path": p})
            file_contents[p] = content[:6000]  # cap per file

    # Include full listing so the LLM knows what exists even if unread
    listing_hint = (
        f"\n\nAll workspace files ({len(all_paths)} total):\n"
        + "\n".join(f"  {p}" for p in all_paths[:50])
        if all_paths
        else "(empty workspace)"
    )

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
                + f"\n\nCoder's change summary:\n{coder_summary}\n"
                + listing_hint
                + f"\n\nFile contents:\n{file_section}\n\n"
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
