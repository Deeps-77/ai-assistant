---
name: onboard_project
description: Capture a project's tech stack, layout, and conventions the first time you work in a repository. Use this when starting work in a new or unfamiliar project so the assistant can recall its structure in later sessions.
---

# Onboard Project

Run this the first time you work in a repository (or when its structure changes significantly).

## Steps

1. List the top-level layout:
   - `ls` the project root.
   - Identify the language and framework (look for `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `requirements.txt`, etc.).
2. Read key entry points and config files (e.g. `README.md`, `main.py`, `app/`, `src/`, CI configs).
3. Detect the test framework (`pytest`, `jest`, `cargo test`, `go test`) and how to run it.
4. Summarize the project in a short profile:
   - **Stack**: language + framework + package manager
   - **Layout**: important directories and what they contain
   - **Conventions**: naming, formatting, import style observed
   - **Test command**: the exact command to run the suite
5. Persist the profile to memory (the assistant's `projectMemory` store) under key `profile` so future sessions can recall it without re-scanning.

## Output

A concise markdown profile the user can review. Example:

```
## Project Profile: ai-assistant
- Stack: Python 3.12, LangGraph, FastAPI
- Layout: graph.py (orchestration), agents.py (nodes), file_tools.py (IO)
- Conventions: TypedDict state, tool-calling agents, no comments
- Test command: uv run pytest tests/ -v
```
