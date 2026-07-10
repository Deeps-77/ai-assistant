# Phase 1 — AI Software Delivery Team

## 1. Project Overview

An **AI-powered multi-agent software delivery system** built on [LangGraph](https://langchain-ai.github.io/langgraph/). Simulates a software development team using LLM agents to:

1. Analyze a plain-text requirement
2. Break it into user stories and backend modules
3. Design the system architecture
4. Generate production-ready code module by module (in **parallel** via worker subgraph)
5. Review and iteratively fix code until it passes quality checks
6. Generate pytest unit tests (deferred to per-module sandbox workers)
7. Run tests in isolated sandboxes, fix failures
8. Compile everything into a delivery package

All agents communicate through a shared **state** (`SoftwareState`) and the workflow is a directed state graph with conditional routing.

---

## 2. Technology Stack

| Component | Technology |
|---|---|
| Language | Python 3.12+ |
| LLM Framework | LangChain 1.3+ |
| Graph Orchestration | LangGraph 1.2+ |
| LLM Providers | Ollama / LM Studio (via `--provider`) |
| Data Validation | Pydantic v2 |
| Environment | `python-dotenv` |
| Package Manager | `uv` |
| Observability | Built-in `Tracer` (token counts, cost, JSONL logs) |

---

## 3. Quick Start

```bash
# Install
uv sync

# Run (Ollama default)
uv run main.py --requirement "Build a todo app"

# Run with LM Studio
uv run main.py --requirement "Build a todo app" \
  --provider lm_studio \
  --llm-model "qwen/qwen3-4b" \
  --llm-base-url "http://127.0.0.1:1234/v1"

# Run with config file
uv run main.py --config config.yaml

# Run tests
uv run pytest tests/
```

---

## 4. Project Structure

```
ai-assistant/
├── main.py                  # Entry point + config → state mapping
├── config.py                # WorkflowConfig (Pydantic) + CLI/YAML/JSON parsing
├── state.py                 # SoftwareState, WorkerState, Pydantic models, reducers
├── agents.py                # All agent node functions (~2000 lines)
├── graph.py                 # LangGraph StateGraph + routing
├── file_tools.py            # File I/O + @tool decorators
├── prompts.py               # ChatPromptTemplate definitions
├── resilience.py            # add_retry_to_llm, with_retry decorator
├── sandbox.py               # Legacy sandbox (v1)
├── sandbox_agent/           # V2 sandbox infra (environments, detector)
├── observability/
│   ├── __init__.py
│   └── tracing.py           # Tracer, @trace_node, BudgetExceeded
├── scripts/
│   ├── __init__.py
│   └── compile_reqs.py      # uv pip compile wrapper
├── tests/
│   └── test_graph_suite.py  # Unit + graph topology + tracing tests
├── docs/
│   └── Phase-1.md           # This document
├── req.txt                  # Compiled dependencies (uv pip compile)
├── pyproject.toml
└── uv.lock
```

---

## 5. State Schema

### `SoftwareState` (TypedDict) — main graph

| Category | Field | Type | Reducer | Description |
|---|---|---|---|---|
| **Input** | `requirement` | `str` | replace | Raw user requirement |
| | `tech_stack` | `Optional[str]` | replace | e.g. "Python/FastAPI" |
| **Planning** | `stories` | `List[str]` | replace | User stories from Planner |
| | `architecture` | `Optional[str]` | replace | Flattened architecture doc |
| | `modules` | `List[str]` | replace | All module names |
| | `quality_guide` | `Optional[str]` | replace | Quality rules for coder/fixer |
| **Execution** | `pending_modules` | `List[str]` | **replace** | Modules not yet processed |
| | `completed_modules` | `Annotated[List, _append_list]` | append | Modules finished |
| | `batch_modules` | `List[str]` | **replace** | Current parallel batch |
| **Code** | `generated_code` | `Annotated[Dict, operator.or_]` | merge | module → source code |
| | `tests` | `Annotated[Dict, operator.or_]` | merge | module → test code |
| **Review** | `review_score` | `Annotated[Optional[int], _max_score]` | max | Last review score (1-10) |
| | `review_issues` | `Annotated[List, _append_list]` | append | Issues from last review |
| | `fix_attempts` | `Annotated[int, _max_int]` | max | Fix attempts for current module |
| | `score_history` | `Annotated[List[int], _append_int_list]` | append | Score history for convergence |
| **Config** | `max_fix_attempts` | `int` | replace | Max retries (default: 3) |
| | `review_threshold` | `int` | replace | Pass threshold (default: 7) |
| | `adaptive_threshold` | `bool` | replace | Auto-lower threshold when stuck |
| | `execution_mode` | `str` | replace | "parallel" or "sequential" |
| | `max_retries` | `int` | replace | LLM transient retry count |

### `WorkerState` (TypedDict) — per-module subgraph

Used by the parallel worker subgraph. One instance per module. No reducers — each worker is isolated.

| Field | Type | Source |
|---|---|---|
| `module_name` | `str` | Dispatched from SoftwareState |
| `architecture`, `stories`, `quality_guide`, `tech_stack` | ... | From parent state |
| `generated_code` | `Dict[str, str]` | Populated by worker_coder/fixer |
| `review_score`, `review_issues`, `fix_attempts`, `score_history` | ... | Review cycle |
| `max_fix_attempts`, `review_threshold` | `int` | Copied from config |

---

## 6. Graph Architecture

### Node Flow (simplified)

```
[START]
   │
   ├── (analyze/update) → project_reader → project_analyzer ──┐
   └── (create_new) ──────────────────────────────────────────┘
   │
   ▼
Planner → Architect → Quality Gen → Project Init
   │
   ├── (parallel) → Dispatcher ──→ [Worker Subgraph × N] ──→ Batch Check ──→ Human Review
   │                                                           │
   └── (sequential) → Backend Lead → Module Planner → Coder → Reviewer → Fixer ~
                                                                           │
                                                     Human Review ←───────┘
   │
   ▼
QA → Sandbox Dispatcher → [Sandbox Worker × N] → Delivery → [END]
```

### Worker Subgraph (per module, parallel)

```
Worker Entry
   │
   ▼
Worker Module Planner
   │
   ▼
Worker Coder  (uses tool_llm with write_file_tool / create_directory_tool)
   │
   ▼
Worker Reviewer
   ├── (score ≥ threshold) → Worker Complete → return to Batch Check
   └── (score < threshold) → Worker Fixer → Worker Coder (loop, max 3 attempts)
```

### Routing Functions

| Function | Returns | Logic |
|---|---|---|
| `route_by_mode` | `"planner"` or `"project_reader"` | Based on `mode` field |
| `route_after_dispatcher` | `"batch_sender"` or `"human_review"` | If `batch_modules` non-empty |
| `route_after_batch_check` | `"dispatcher"` or `"human_review"` | If `pending_modules` non-empty |
| `route_after_review` | `"fixer"` or `"complete_module"` | Score vs threshold + convergence |
| `_route_after_worker_review` | `"worker_fixer"` or `"worker_complete"` | Same logic for worker subgraph |
| `route_after_human` | `"qa"`, `"dispatcher"`, or `"backend_lead"` | Based on approval + execution mode |
| `route_by_execution_mode` | `"dispatcher"` or `"backend_lead"` | Parallel vs sequential |
| `route_after_backend_lead` | `"module_planner"` or `"human_review"` | Sequential fallback path |

### Convergence Detection

Both `route_after_review` and `_route_after_worker_review` detect stuck scores:
- **If `adaptive_threshold` is enabled** and the last two scores are equal below threshold, the passing bar is lowered to the current score (breaks the loop).
- **If 4+ scores exist** and the best of the last 2 is ≤ best of the 2 before that, force-complete.
- **If 3 identical scores**, force-complete.

---

## 7. Tool Calling Architecture

Agents write files using LangChain `@tool`-decorated functions:

| Tool | Purpose |
|---|---|
| `write_file_tool` | Write code content to a file path |
| `create_directory_tool` | Create a directory |
| `read_file_tool` | Read file content (for analyze/update modes) |

The `_execute_tool_calls()` helper in `agents.py` processes LLM responses with tool calls. If a tool-calling model returns no `write_file_tool` calls (e.g. only creates directories), the system re-prompts with a reinforcement message before falling back to the plain LLM.

---

## 8. Observability

The `observability/tracing.py` module provides:

- **`Tracer`** — Records per-node duration, estimated tokens, cost. Outputs:
  - Stderr summary at end of run
  - `logs/trace_<run_id>.jsonl` file
- **`@trace_node`** — Decorator to wrap graph-node functions
- **Budget cap** — Set `OBSERVABILITY_BUDGET_USD` env var to raise `BudgetExceeded` when exceeded
- **Token estimation** — Uses `tiktoken` if available, else `chars/4` heuristic

---

## 9. Resilience

| Layer | Mechanism |
|---|---|
| **Transient LLM failures** | `add_retry_to_llm()` wraps base LLM with exponential backoff + jitter (ConnectionError, TimeoutError, OSError). Covers ALL ~25 invoke sites. |
| **Tool-call fallback** | When tool_llm returns only directory calls (no file writes), re-prompts with reinforced instruction. Then falls to plain LLM text output. |
| **Empty code guard** | If all paths fail, inserts `# TODO: implement` placeholder. |
| **Review convergence** | Detects stuck scores and force-completes module. |
| **`with_retry` decorator** | `@with_retry(max_attempts=3, backoff=1.0)` for standalone functions. |
| **`max_retries` CLI flag** | Configurable via `--max-retries N` or `WorkflowConfig.max_retries`. |

---

## 10. Configuration

```bash
# All CLI flags
uv run main.py \
  --requirement "..." \
  --project-path ./outputs/project \
  --tech-stack "Python/FastAPI" \
  --mode create_new \
  --provider ollama \
  --llm-model "gemma4:31b-cloud" \
  --llm-base-url "https://ollama.com" \
  --execution-mode parallel \
  --max-concurrent-modules 5 \
  --max-fix-attempts 3 \
  --review-threshold 7 \
  --adaptive-threshold \
  --max-retries 2 \
  --sandbox-enabled \
  --sandbox-mode local
```

Config file support: `--config config.yaml` or `--config config.json`.

---

## 11. Current Status

| Feature | Status |
|---|---|
| Parallel module generation (worker subgraph) | ✅ |
| Tool-calling coder/fixer (write_file_tool) | ✅ |
| Plain LLM fallback (non-tool models) | ✅ |
| Review-fix convergence detection | ✅ |
| Adaptive threshold | ✅ |
| Per-module parallel test generation | ✅ |
| Sandbox test execution (parallel) | ✅ |
| LM Studio provider | ✅ |
| Human-in-the-loop review | ✅ |
| Analyzer/update mode | ✅ |
| CLI + YAML/JSON config | ✅ |
| Retry on transient LLM failures | ✅ |
| Observability tracing + cost tracking | ✅ |
| `uv pip compile` script | ✅ |
| Tests (reducers, routing, graph topology) | ✅ |

### Known Limitations

- **req.txt** is generated by `uv pip compile pyproject.toml -o req.txt`. Run `uv run compile-reqs` to regenerate.
- Models may occasionally produce only `create_directory_tool` calls without writing files. The re-prompt usually recovers, but a small model may need multiple tries.
- Tests require no API keys but the E2E test (`RUN_E2E=1`) needs a fake model factory wired up.
