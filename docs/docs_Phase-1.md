# Phase-1 Design Notes & Roadmap

> Updated 2026-07-09 to match the **current implementation** (supersedes the
> older sequential-graph description). Items marked ✅ are done; ⬜ are TODO.

## 1. Goal

Take a natural-language requirement → produce a runnable, unit-tested software
project via a coordinated set of LLM agents, sandboxed execution, and
self-review, packaged for human delivery.

## 2. Architecture (current)

`StateGraph` (`graph.py`) with `AgentState` (`state.py`):

```
requirement_reader
        │
   project_reader (update mode only: reads existing project)
        │
   project_analyzer ──route──► planner (update: regenerate stories)
        │
     planner ──► architect ──► human_review (CLI input())
        │
  project_dispatcher  ── Send() fan-out ──► [ module_worker → sandbox_tester →
                                                  senior_reviewer ] × N  (subgraph)
        │  (reducer-merges worker_results / completed_modules / tests)
   [...per-module review routing...]
        │
   delivery  ──► delivery_packager (writes delivery_package.md)
```

Key mechanics:
- **Parallelism:** `Send()` dispatches one `module_worker` subgraph instance
  per module; each returns a dict merged by reducers (`worker_results_add`,
  `merge_dicts`).
- **Sandbox:** `sandbox_agent/` runs generated code in `local` (subprocess) or
  `docker` mode; classifier splits errors into *fatal* vs *fixable*; fixable
  errors drive a patch loop bounded by `--max-fix-attempts`.
- **Review:** `senior_reviewer` (LLM) critiques code and may request changes;
  routing converges after N attempts or when threshold met.
- **Providers:** Ollama / LM Studio via `langchain-ollama`; OpenAI/Anthropic
  fallback available through `langchain-openai` / `langchain-anthropic`.
- **Resilience:** `resilience.py` retry-with-backoff + parse-fallback chain.
- **Observability:** `observability/tracing.py` (NEW) — per-node timing, token
  counts, est. cost, JSONL log, optional global budget cap.

## 3. Status table

| Capability                         | Status | Notes |
|------------------------------------|--------|-------|
| Parallel module fan-out (`Send`)   | ✅ | reducer merge |
| Multi-language sandbox (local/docker) | ✅ | py/node/rust/go/java/.net |
| Fatal vs fixable error triage      | ✅ | |
| LLM senior review + patch loop     | ✅ | same-model self-review |
| analyze / update modes             | ✅ | update = full rebuild, not surgical |
| Multi-provider (Ollama/LM Studio)  | ✅ | OpenAI/Anthropic fallback wired via deps |
| Retry / backoff / parse fallback   | ✅ | `resilience.py` |
| FastAPI `/run` endpoint            | ✅ | |
| **Graph test suite**               | ✅ | `tests/test_graph_suite.py` (NEW) |
| **Tracing + cost logging**         | ✅ | `observability/tracing.py` (NEW) |
| Real HITL via `interrupt()`        | ⬜ | currently blocking `input()` |
| Git / PR delivery                  | ⬜ | writes to disk + markdown only |
| Runnable deliverable acceptance test | ⬜ | only per-module unit tests gate |
| Activate `adaptive_threshold`      | ⬜ | dead config; not used in routing |
| Global LLM budget / abort guards   | ⬜ | per-module caps only (logging cap added) |
| Cross-run memory / learning        | ⬜ | `MemorySaver` is in-memory only |
| Streaming / async / WebSocket      | ⬜ | `app.invoke` is sync |
| Independent verification (stronger model / RAG) | ⬜ | |

## 4. Roadmap (priority order)

1. **Replace `input()` HITL with `interrupt()`-based gates** (architecture →
   per-module → pre-delivery). Unblocks the API and resumability. *(gates the
   rest)*
2. **Version control integration** — branch → write files → commit → open PR;
   run CI if present.
3. **Make the deliverable runnable** — install deps in `project_path`, run an
   acceptance/health check, gate delivery on a passing smoke test (not just
   self-written unit tests, and only when `--sandbox-enabled`).
4. **Activate `adaptive_threshold`** in `route_after_review` /
   `route_after_worker_review`; add a true global call/cost budget that aborts.
5. **Escalation + memory** — route hard modules to a stronger model; persist a
   fix/pattern corpus across runs.
6. **Streaming / async** — wrap `app.ainvoke`, add a WebSocket or LangGraph
   Studio config for live progress.
7. **Layered model routing** — cheap model for Planner/Architect, strong coder
   model for Code/Review; wire the OpenAI/Anthropic fallback path.

## 5. Testing strategy

- `pytest tests/` runs pure-python checks (reducers, resilience, file tools,
  routing-returns-valid-node, graph topology, tracing) with **no API keys**.
- `RUN_E2E=1 pytest tests/` runs a full graph pass with a fake model.
- Each graph run now emits `logs/trace_<run_id>.jsonl` for regression
  comparison of cost/latency as the roadmap items above land.

## 6. Doc hygiene

- `README.md` — was 0 bytes; replaced with the current architecture/usage doc.
- `req.txt` — regenerated to match `pyproject.toml`; frozen via `uv pip compile`.
- This file — rewritten to describe the parallel/sandbox/HITL graph actually
  shipped (the previous version described an older sequential graph).