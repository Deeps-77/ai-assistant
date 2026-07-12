# AI Software Delivery Team

Multi-agent system powered by LLMs that plans, codes, reviews, fixes, tests, and delivers software from a plain-text requirement.

## Quick Start

```bash
uv sync

# Batch delivery (existing pipeline)
uv run main.py --requirement "Build a todo app"

# Interactive assistant (new)
uv run python -m assistant.repl --project-path .
```

## Interactive Assistant

The project wraps the delivery pipeline in a `deepagents` interactive assistant.
It does lightweight in-repo work itself (read/edit files, run shell & tests) and
delegates large multi-file delivery to the wrapped pipeline through a `task`
sub-agent.

```bash
# Pick a runtime profile
uv run python -m assistant.repl --profile ollama      # cloud/remote Ollama, model gemma4:31b-cloud
uv run python -m assistant.repl --profile local       # LM Studio OpenAI API, model qwen/qwen3-4b

# Inside the session
you> analyze this repository          # read-only report, no files changed
you> build a REST API for a todo list
you> add JWT authentication to the users module
/help   /mode   /clear   /exit
```

`analyze` mode is fully read-only: it reads the project, produces an LLM prose
report (tech stack, modules, issues, recommendations), and writes nothing.
`build`/`create`/`update`/`add` requests run the generative delivery pipeline.

### Model configuration

Everything is configurable via environment variables. The `local` profile targets
**LM Studio** (an OpenAI-compatible API at `http://localhost:1234/v1`): the
orchestrator uses the `openai` provider, and the wrapped delivery pipeline uses
its own `lm_studio` provider.

| Variable | Default (ollama) | Default (local) | Meaning |
| --- | --- | --- | --- |
| `ASSISTANT_PROFILE` | `ollama` | `local` | Runtime profile selector |
| `ASSISTANT_MODEL` | `gemma4:31b-cloud` | `qwen/qwen3-4b` | Orchestrator model |
| `ASSISTANT_PROVIDER` | `ollama` | `openai` | Orchestrator chat provider |
| `ASSISTANT_BASE_URL` | `OLLAMA_BASE_URL` | `http://localhost:1234/v1` | Orchestrator endpoint |
| `ASSISTANT_API_KEY` | _(none)_ | `lm-studio` | API key for the endpoint |
| `ASSISTANT_CTX_SIZE` | `32768` (ollama) | _(none)_ | Ollama context window (`num_ctx`); auto-applied. LM Studio/OpenAI is server-controlled. |
| `DELIVERY_CTX_SIZE` | (same as `ASSISTANT_CTX_SIZE`) | | Context window for the wrapped delivery pipeline |
| `ASSISTANT_MAX_TOKENS` | _(endpoint default)_ | | Cap generation length for the orchestrator |
| `ASSISTANT_TEMPERATURE` | _(endpoint default)_ | | Sampling temperature for the orchestrator |
| `DELIVERY_MODEL` | (same as `ASSISTANT_MODEL`) | | Override the wrapped pipeline's model |
| `ASSISTANT_DELIVERY_PROVIDER` | `ollama` | `lm_studio` | Provider for the delivery pipeline |
| `ASSISTANT_DELIVERY_BASE_URL` | (same as `ASSISTANT_BASE_URL`) | | Endpoint for the delivery pipeline |
| `ASSISTANT_TECH_STACK` | _(auto)_ | | Hint the stack for new projects |
| `ASSISTANT_EXECUTION_MODE` | `parallel` | | `parallel` | `sequential` |
| `ASSISTANT_SANDBOX` | `0` | | Enable sandboxed test execution (`1`) |
| `ASSISTANT_INTERRUPT_SHELL` | `1` | | Require approval before shell commands |

Local profile alternative model: set `ASSISTANT_MODEL=google/gemma-4-e4b`
(use the exact model identifier loaded in LM Studio).

### Context window / token budget

The deep-agent harness ships a large system prompt (filesystem tools, skills,
sub-agent description, planning/todo instructions). On small local models this
can consume most of the context window, leaving little room to generate a tool
call — the model then returns empty output (`finish_reason: "length"`).

If you see *"no response generated"*:

- The REPL now prints the **actual model diagnostics** (e.g.
  `finish_reason="length", prompt_tokens=8153`), so you can tell whether it was
  context truncation vs. the model returning nothing.
- **Ollama**: the assistant auto-sets `num_ctx` (default `32768`). If the model
  fails to load (OOM), lower it with `ASSISTANT_CTX_SIZE=16384`. The delivery
  pipeline honors the same value via `DELIVERY_CTX_SIZE`.
- **LM Studio / OpenAI**: set the context length in the server/UI (e.g. 16k–32k).
  `ASSISTANT_CTX_SIZE` is ignored for these providers.
- `qwen3` models spend context on reasoning; disable thinking in LM Studio if the
  agent loop needs more room, or use a larger model for the orchestrator.

### HTTP server

```bash
uv run python -m assistant.server --project-path . --port 8000
# POST /run  {"message": "...", "thread_id"?: "..."}
# POST /resume {"thread_id": "...", "decisions": [...]}
# GET  /health
```

When a destructive action needs approval the `/run` endpoint returns HTTP 202
with the interrupt payload; approve via `/resume`.

## Features

- **Parallel module generation** — independent modules coded concurrently via LangGraph `Send`
- **Tool-calling agents** — writes files via `write_file_tool`/`create_directory_tool`, falls back to plain LLM text output
- **Review-fix loop** — iterative improvement with convergence detection and adaptive threshold
- **Sandbox test execution** — runs tests in isolated environments, fixes failures
- **Resilience** — automatic retry on transient LLM failures (configurable via `--max-retries`)
- **Observability** — per-node duration, token counts, cost tracking with JSONL logs
- **Ollama & LM Studio** — provider-agnostic, switch with `--provider lm_studio`

## Documentation

- [Phase 1 Architecture](docs/Phase-1.md) — full architecture, state schema, graph topology, configuration reference
- [Test Suite](tests/test_graph_suite.py) — unit tests for reducers, resilience, routing, graph topology, and tracing (no API keys needed)

## Development

```bash
# Regenerate requirements
uv run compile-reqs

# Run tests
uv run pytest tests/ -v
```
