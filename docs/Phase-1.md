# Phase 1 — AI Software Delivery Team

## 1. Project Overview

This project is an **AI-powered multi-agent software delivery system** built on [LangGraph](https://langchain-ai.github.io/langgraph/). It simulates a software development team using LLM agents to:

1. Analyze a plain-text requirement
2. Break it into user stories and backend modules
3. Design the system architecture
4. Generate production-ready FastAPI code module by module
5. Review and iteratively fix code until it passes quality checks
6. Generate pytest unit tests
7. Compile everything into a single delivery package (markdown)

All agents communicate through a shared **state** (`SoftwareState`) and the workflow is a directed state graph with conditional routing.

---

## 2. Technology Stack

| Component | Technology |
|---|---|
| Language | Python 3.12+ |
| LLM Framework | LangChain 0.2+ |
| Graph Orchestration | LangGraph 0.2+ |
| LLM Provider | Ollama (cloud) |
| Current Model | `gemma4:31b-cloud` |
| Data Validation | Pydantic v2 |
| Environment | `python-dotenv` |
| Package Manager | `uv` (lockfile: `uv.lock`) |

---

## 3. Quick Start

### Prerequisites
- Python 3.12+
- `uv` package manager (or `pip`)
- Ollama account / API key

### Setup

```bash
# Clone and enter the project
cd ai-assistant

# Create .env file
# OLLAMA_API_KEY=<your-key>
# OLLAMA_BASE_URL=https://ollama.com
# OLLAMA_MODEL=gemma4:31b-cloud

# Install dependencies
uv sync

# Run the workflow
uv run main.py
```

### Output

The workflow produces `outputs/delivery_package.md` containing:
- Requirement & user stories
- Architecture document (tech stack, DB schema, API endpoints, folder tree, architecture diagram)
- Generated source code for each module
- Generated pytest tests for each module

---

## 4. Project Structure

```
ai-assistant/
├── .env                    # Ollama configuration
├── .python-version         # Python version pinning
├── pyproject.toml          # Project metadata & dependencies
├── uv.lock                 # Lock file
├── state.py                # SoftwareState TypedDict + Pydantic models
├── agents.py               # All agent node functions
├── graph.py                # LangGraph StateGraph construction & routing
├── main.py                 # Application entry point
├── outputs/                # Runtime output directory
│   └── delivery_package.md # Final delivery document
└── docs/
    └── Phase-1.md          # This document
```

---

## 5. State Schema (`state.py`)

### `SoftwareState` (TypedDict)

All agents read from and write to a shared `SoftwareState` dictionary. Fields are grouped by lifecycle phase:

| Category | Field | Type | Description |
|---|---|---|---|
| **Input** | `requirement` | `str` | Raw user requirement |
| **Planning** | `stories` | `List[str]` | User stories from Planner |
| | `architecture` | `Optional[str]` | Flattened architecture document |
| | `modules` | `List[str]` | All module names |
| | `quality_guide` | `Optional[str]` | Quality rules injected into coder/fixer prompts |
| **Execution** | `pending_modules` | `List[str]` | Modules not yet processed |
| | `completed_modules` | `List[str]` | Modules finished and accepted |
| | `current_module` | `Optional[str]` | Module currently being worked on |
| | `module_plan` | `Optional[str]` | Per-module file plan (from Module Planner) |
| **Code** | `generated_code` | `Dict[str, str]` | `module_name → source code` |
| | `tests` | `Dict[str, str]` | `module_name → test code` |
| **Review** | `review_score` | `Optional[int]` | Last review score (1-10) |
| | `review_issues` | `List[str]` | Issues from last review |
| | `fix_attempts` | `int` | Number of fix attempts for current module |
| | `max_fix_attempts` | `int` | Max retries before force-complete (default: 3) |
| **Output** | `delivery_package` | `Optional[str]` | Final compiled markdown |

### Pydantic Models (Structured LLM Output)

| Model | Used By | Fields |
|---|---|---|
| `ModuleList` | Planner | `stories: List[str]`, `modules: List[str]` |
| `ArchitectureDoc` | Architect | `tech_stack`, `db_schema`, `api_endpoints`, `folder_structure`, `architecture_diagram` (all `str`) |
| `ModuleFile` | Module Planner | `path`, `purpose`, `exports: List[str]` |
| `ModulePlan` | Module Planner | `module_name`, `files: List[ModuleFile]`, `dependencies: List[str]`, `api_routes: List[str]` |
| `CodeReview` | Reviewer | `score: int`, `issues: List[str]`, `logic_correctness: str`, `security_check: str` |

---

## 6. Graph Architecture (`graph.py`)

### Node Flow

```
[START]
   |
   v
Planner ──────────────────────────────────────→ stories + modules
   |
   v
Architect ────────────────────────────────────→ tech_stack, db_schema, api_endpoints,
   |                                              folder_structure (tree), architecture_diagram (ASCII)
   v
Backend Lead ──→ picks next pending module
   |
   ├── (module available) ──→ Module Planner
   |                              |
   |                              v
   |                          Module Coder
   |                              |
   |                              v
   |                          Reviewer
   |                          ↙       ↘
   |                     Fixer     Complete Module
   |                      ↘         ↙
   |                    (loop: max 3 attempts)
   |                              |
   └── (no modules) ──────────────┤
                                   |
                                   v
                                QA Agent ──→ pytest tests
                                   |
                                   v
                              Delivery ──→ delivery_package.md
                                   |
                                   v
                                 [END]
```

### Conditional Routing

**`route_after_backend_lead`** — Decides whether to process another module or move to QA:
- `current_module` is set → route to `module_planner`
- `current_module` is `None` (no pending modules) → route to `qa`

**`route_after_review`** — Decides whether to fix or accept the module:
- `score >= 8` → pass, route to `complete_module`
- `fix_attempts >= max_attempts` (3) → force-complete, route to `complete_module`
- Otherwise → route to `fixer` for another fix iteration

### Edges Summary

| From | To | Type |
|---|---|---|
| `planner` | `architect` | Fixed |
| `architect` | `backend_lead` | Fixed |
| `backend_lead` | `module_planner` or `qa` | Conditional |
| `module_planner` | `module_coder` | Fixed |
| `module_coder` | `reviewer` | Fixed |
| `reviewer` | `fixer` or `complete_module` | Conditional |
| `fixer` | `reviewer` | Fixed (loop) |
| `complete_module` | `backend_lead` | Fixed (next module or finish) |
| `qa` | `delivery` | Fixed |
| `delivery` | `END` | Fixed |

### Checkpointing

The graph is compiled with `MemorySaver` checkpointer, enabling thread-level state persistence (configured via `thread_id` in the config).

---

## 7. Agent Node Reference (`agents.py`)

### 7.1 Planner

| Attribute | Detail |
|---|---|
| **Purpose** | Analyze the requirement, produce user stories and module names |
| **LLM** | `planner_llm` — structured output via `ModuleList` (json_mode) |
| **Prompt highlights** | Requests flat JSON with `stories` and `modules` arrays |
| **Reads** | `state["requirement"]` |
| **Writes** | `stories`, `modules`, `pending_modules`, `completed_modules`, `max_fix_attempts` |
| **Fallback** | Catches `OutputParserException` → re-invokes with plain LLM → `_flatten_planner()` maps alternative field names (`user_stories`, `backend_modules`) |
| **Safe default** | If fallback also fails, returns `["app"]` as single module |

### 7.2 Architect

| Attribute | Detail |
|---|---|
| **Purpose** | Design the full system architecture |
| **LLM** | `architect_llm` — structured output via `ArchitectureDoc` (json_mode) |
| **Prompt highlights** | Requests 5 flat string fields; `folder_structure` must be multi-line tree; `architecture_diagram` must be ASCII component/flow diagram |
| **Reads** | `state["stories"]`, `state["modules"]` |
| **Writes** | `architecture` (flattened markdown string), `quality_guide` (constant) |
| **Fallback** | Catches `OutputParserException` → plain LLM → `_flatten_architecture()` unwraps nested keys (`system_architecture`, `architecture`, `arch`) |

### 7.3 Backend Lead (Dispatcher)

| Attribute | Detail |
|---|---|
| **Purpose** | Pick the next pending module from the queue |
| **Logic** | Pops first item from `pending_modules`, sets `current_module` |
| **Termination** | If `pending_modules` is empty, sets `current_module = None` → triggers QA phase |
| **Reads** | `pending_modules` |
| **Writes** | `current_module`, `pending_modules` |

### 7.4 Module Planner

| Attribute | Detail |
|---|---|
| **Purpose** | Plan the files needed for the current module |
| **LLM** | `module_planner_llm` — structured output via `ModulePlan` (json_mode) |
| **Prompt highlights** | Requests file-by-file plan with `path`, `purpose`, `exports` per file; also outputs `dependencies` and `api_routes` |
| **Reads** | `current_module`, `architecture`, `quality_guide` |
| **Writes** | `module_plan` (flattened string) |
| **Fallback** | `_flatten_module_plan()` — maps alternative field names (`name`, `deps`, `routes`) |

### 7.5 Module Coder

| Attribute | Detail |
|---|---|
| **Purpose** | Write production FastAPI code for the current module |
| **LLM** | Plain `llm` (no structured output — returns raw code) |
| **Prompt highlights** | Receives `architecture`, `module_plan`, and `quality_guide`; asks for multi-file code with `# --- filename.py ---` separators |
| **Reads** | `current_module`, `architecture`, `module_plan`, `quality_guide` |
| **Writes** | `generated_code[module]`, `fix_attempts` (reset to 0) |
| **Guard** | If LLM returns empty/whitespace content, inserts a `# TODO: implement` placeholder |

### 7.6 Reviewer

| Attribute | Detail |
|---|---|
| **Purpose** | Score generated code (1-10) and list issues |
| **LLM** | `reviewer_llm` — structured output via `CodeReview` (json_mode) |
| **Prompt highlights** | Requests flat JSON with `score`, `issues` (array of strings), `logic_correctness`, `security_check` |
| **Reads** | `current_module`, `generated_code[module]` |
| **Writes** | `review_score`, `review_issues` |
| **Guard** | If `code` is empty, returns score=1 without calling LLM |
| **Fallback** | `_flatten_review()` — maps `quality_score`, `logic_correctness_analysis`, `security_analysis`; extracts `description` from dict-type issues |

### 7.7 Fixer

| Attribute | Detail |
|---|---|
| **Purpose** | Fix code based on reviewer issues |
| **LLM** | Plain `llm` |
| **Prompt highlights** | Gets current code + issues list + `quality_guide`; returns corrected code |
| **Reads** | `current_module`, `generated_code[module]`, `review_issues`, `fix_attempts`, `quality_guide` |
| **Writes** | `generated_code[module]`, `fix_attempts` (incremented) |

### 7.8 Complete Module

| Attribute | Detail |
|---|---|
| **Purpose** | Mark module as done, reset per-module state for next module |
| **Logic** | Appends `current_module` to `completed_modules`; resets `module_plan`, `review_score`, `review_issues`, `fix_attempts`; sets `current_module = None` |
| **Reads** | `current_module`, `completed_modules` |
| **Writes** | `completed_modules`, `current_module`, `module_plan`, `review_score`, `review_issues`, `fix_attempts` |

### 7.9 QA Agent

| Attribute | Detail |
|---|---|
| **Purpose** | Generate pytest unit tests for all completed modules |
| **LLM** | Plain `llm` (once per module) |
| **Prompt highlights** | Requests comprehensive pytest tests with edge cases |
| **Reads** | `generated_code` (all entries) |
| **Writes** | `tests[module]` for each module |

### 7.10 Delivery

| Attribute | Detail |
|---|---|
| **Purpose** | Compile everything into a final delivery markdown file |
| **Sections** | Requirement → User Stories → Completed Modules → Architecture → Source Code → Test Code |
| **Persistence** | Writes to `outputs/delivery_package.md` (path configurable via `OUTPUT_DIR` env var) |
| **Reads** | All state fields |
| **Writes** | `delivery_package` |

---

## 8. Quality Guide

A constant `QUALITY_GUIDE` is defined in `agents.py` and injected into the Module Coder and Fixer prompts. It covers:

| Category | Rules |
|---|---|
| **Python & FastAPI** | `datetime.now(timezone.utc)` over deprecated `utcnow()`; DB sessions via `Depends(get_db)`; async def endpoints; type hints everywhere |
| **Security** | No hardcoded secrets; passwords hashed with bcrypt; JWT with expiration; input validation via Pydantic; no raw SQL |
| **Architecture** | Separate files per concern (schemas, models, crud, routes); CRUD layer never raises HTTPException; dependency injection for services |
| **Database** | Commits in API layer not CRUD; eager-load to avoid N+1; `order_by` on paginated queries; bounded pagination params |
| **Code Quality** | No unused imports; no bare `except:`; no mutable defaults; enums for fixed value sets |

---

## 9. Error Handling & Resilience

| Scenario | Handling |
|---|---|
| **LLM returns wrong JSON field names** | `_flatten_*` helpers map alternative common names (e.g., `quality_score` → `score`, `system_architecture` → wrapper unwrap) |
| **LLM returns nested JSON instead of flat** | `_flatten_architecture` unwraps `system_architecture` / `architecture` / `arch` wrapper keys |
| **LLM returns non-JSON** | `json.JSONDecodeError` caught → safe defaults returned (empty plan, empty architecture, single-module planner) |
| **LLM returns empty code** | Placeholder `# TODO: implement` inserted instead of empty string |
| **Reviewer gets empty code** | Returns score=1 without calling LLM |
| **Review loop exceeds max attempts** | Force-completes module with current score (avoids infinite loop) |
| **Windows console can't print emoji** | `sys.stdout.reconfigure(encoding="utf-8")` in `main.py` |

---

## 10. LLM Configuration

The app uses Ollama cloud models configured via `.env`:

```env
OLLAMA_API_KEY=<key>
OLLAMA_BASE_URL="https://ollama.com"
OLLAMA_MODEL="gemma4:31b-cloud"
```

Four structured-output LLMs are created from the base model:

```python
planner_llm       = llm.with_structured_output(ModuleList,       method="json_mode")
architect_llm     = llm.with_structured_output(ArchitectureDoc,  method="json_mode")
module_planner_llm= llm.with_structured_output(ModulePlan,       method="json_mode")
reviewer_llm      = llm.with_structured_output(CodeReview,       method="json_mode")
```

- **Temperature**: 0 (deterministic)
- **Method**: `json_mode` (broad Ollama compatibility)

---

## 11. Current Behavior & Known Limitations

### Scores from Latest Run

| Module | Initial Score | Final Score | Attempts Used |
|---|---|---|---|
| auth | 4 | 7 | 3 |
| users | 5 | 6 | 3 |
| inventory | 5 | 7 | 3 |

- **No module passed** the score ≥ 8 threshold on its own; all were force-completed after 3 fix attempts.
- Scores improved by 1-3 points per module through fix iterations, suggesting the fixer helps but cannot bridge the gap to passing.
- With `max_fix_attempts=3`, a full 3-module run takes approximately 8-12 minutes total (30+ LLM calls).

### Common Reviewer Issues (all modules)
1. Hardcoded secrets / default config values
2. Deprecated `datetime.utcnow()` usage
3. Broken transaction management (commits in wrong layer)
4. Race conditions in concurrent DB operations
5. Missing input validation / weak password rules
6. Generic exception handling (bare `except:`)
7. Leaking HTTPExceptions from CRUD/service layers
8. Inefficient queries (N+1, no pagination bounds)

---

## 12. What Needs to Be Completed (Future Work)

### Immediate Quality Improvements
- [ ] **Model upgrade** — Switch from `gemma4:31b-cloud` to `qwen2.5-coder:7b` or `:14b` for better code generation
- [ ] **Lower review threshold** — Change from 8 to 7 so modules reaching 7 pass earlier (saves fix attempts)
- [ ] **Split generated code into separate files** — Currently all code blocks are in one monolithic markdown; write actual `.py` files per module

### Architecture & Engineering
- [ ] **Config file** — Replace hardcoded settings (threshold, max_attempts, model name) with a YAML/JSON config
- [ ] **Human-in-the-loop gates** — Add approval steps before critical transitions (architect → coding, delivery)
- [ ] **Parallel module generation** — Independent modules could be coded concurrently
- [ ] **Async & streaming** — Stream LLM responses for faster feedback
- [ ] **Persistent checkpointing** — Replace `MemorySaver` with SQLite/Postgres for resume capability
- [ ] **Unit tests for the graph itself** — Test routing logic, error handling, and edge cases without LLM calls

### Feature Additions
- [ ] **Non-FastAPI support** — Allow configurable tech stacks beyond FastAPI/PostgreSQL
- [ ] **Multi-language output** — Generate frontend code (React, Vue) alongside backend
- [ ] **Git integration** — Commit generated code to a repo, create PRs, run CI checks
- [ ] **Web UI** — Simple dashboard showing workflow progress, scores, and logs
- [ ] **Custom quality rules** — Allow users to define their own quality guide via config
- [ ] **Docker support** — Containerize the workflow for CI/CD pipelines
- [ ] **Prompt versioning** — Track prompt changes and their effect on scores
