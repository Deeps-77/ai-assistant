# AI Software Delivery Team

Multi-agent system powered by LLMs that plans, codes, reviews, fixes, tests, and delivers software from a plain-text requirement.

## Quick Start

```bash
uv sync
uv run main.py --requirement "Build a todo app"
```

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
