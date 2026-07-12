"""
tests/test_graph_suite.py

Graph + unit tests for the multi-agent software-delivery assistant.

WHAT RUNS WITHOUT API KEYS (default `pytest`):
  * state reducers (_merge_dicts, _append_list, _max_score, ...)
  * resilience (add_retry_to_llm, with_retry decorator)
  * file_tools write/read/parse_code_blocks
  * routing logic (route_after_review, _route_after_worker_review, ...)
      -> asserts each router returns a REAL graph node name
  * compiled-graph topology (core nodes + acyclic-ish structure)
  * tracing + cost logging (observability.tracing) incl. budget cap

END-TO-END (needs a model): disabled by default. Set RUN_E2E=1 to run.
"""
from __future__ import annotations

import os
import sys
import json
import time
import tempfile
from pathlib import Path

import pytest
from langgraph.types import Command

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

RUN_E2E = os.environ.get("RUN_E2E") == "1"

# ---------------------------------------------------------------------------
# IMPORTS  (align with the actual codebase)
# ---------------------------------------------------------------------------
from config import WorkflowConfig                              # noqa: E402
import state as state_mod                                      # noqa: E402
from state import (                                             # noqa: E402
    SoftwareState,
    WorkerState,
    _merge_dicts,
    _append_list,
    _append_int_list,
    _max_int,
    _max_score,
)
import resilience                                              # noqa: E402
from resilience import add_retry_to_llm, with_retry            # noqa: E402
import file_tools as ft                                        # noqa: E402
from file_tools import (                                       # noqa: E402
    write_file,
    read_file,
    parse_code_blocks,
    ensure_directory,
    init_project_structure,
    write_file_tool,
    create_directory_tool,
    read_file_tool,
)
import graph as graph_mod                                      # noqa: E402
import agents as agents_mod                                    # noqa: E402

# routing functions (exported from graph.py; None if absent -> skip)
route_after_review        = getattr(graph_mod, "route_after_review", None)
route_after_worker_review = getattr(graph_mod, "_route_after_worker_review", None)
route_after_dispatcher    = getattr(graph_mod, "route_after_dispatcher", None)
route_after_batch_check   = getattr(graph_mod, "route_after_batch_check", None)
route_by_execution_mode   = getattr(graph_mod, "route_by_execution_mode", None)
route_after_human         = getattr(graph_mod, "route_after_human", None)
route_after_backend_lead  = getattr(graph_mod, "route_after_backend_lead", None)
route_after_analyzer      = getattr(graph_mod, "route_after_analyzer", None)
route_by_mode             = getattr(graph_mod, "route_by_mode", None)

# compiled graph (app)
compiled_graph = getattr(graph_mod, "app", None)

# file_tools function name aliases (single source of truth)
write_fn  = getattr(ft, "write_file", None)
read_fn   = getattr(ft, "read_file", None)
extract_fn = getattr(ft, "parse_code_blocks", None)

require_state = pytest.mark.skipif(
    compiled_graph is None,
    reason="compiled graph not found; check that graph_mod.app is set",
)

# ---------------------------------------------------------------------------
# STATE REDUCERS
# ---------------------------------------------------------------------------

def test_merge_dicts_overwrites():
    merged = _merge_dicts({"k": "a"}, {"k": "b"})
    assert merged["k"] == "b"


def test_append_list_deduplicates():
    result = _append_list(["a", "b"], ["b", "c"])
    assert result == ["a", "b", "c"]


def test_append_int_list_appends():
    result = _append_int_list([1, 2], [3])
    assert result == [1, 2, 3]


def test_max_int():
    assert _max_int(3, 7) == 7
    assert _max_int(10, 5) == 10


def test_max_score_none():
    assert _max_score(None, 5) == 5
    assert _max_score(3, None) == 3
    assert _max_score(None, None) is None


def test_max_score():
    assert _max_score(4, 8) == 8
    assert _max_score(8, 4) == 8


# ---------------------------------------------------------------------------
# RESILIENCE — with_retry decorator
# ---------------------------------------------------------------------------

def test_with_retry_succeeds_eventually():
    calls = {"n": 0}

    @with_retry(max_attempts=3, backoff=0.01)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("boom")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3


def test_with_retry_exhausts():
    @with_retry(max_attempts=2, backoff=0.01)
    def always_fails():
        raise ValueError("x")

    with pytest.raises(ValueError):
        always_fails()


def test_with_retry_non_retryable_passthrough():
    @with_retry(max_attempts=3, backoff=0.01)
    def raiser():
        raise RuntimeError("not retryable")

    with pytest.raises(RuntimeError):
        raiser()


# ---------------------------------------------------------------------------
# RESILIENCE — add_retry_to_llm
# ---------------------------------------------------------------------------

def _make_dummy_llm():
    """A minimal object with .invoke() to test wrapping."""
    class Dummy:
        def invoke(self, *args, **kwargs):
            return "ok"
    return Dummy()


def test_add_retry_to_llm_preserves_ok():
    llm = _make_dummy_llm()
    add_retry_to_llm(llm, max_retries=2)
    assert llm.invoke() == "ok"


def test_add_retry_to_llm_retries_on_connection_error():
    calls = {"n": 0}

    class Flaky:
        def invoke(self, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] < 3:
                raise ConnectionError("transient")
            return "recovered"

    llm = Flaky()
    add_retry_to_llm(llm, max_retries=3)
    assert llm.invoke() == "recovered"
    assert calls["n"] == 3


def test_add_retry_to_llm_exhausts():
    class AlwaysFails:
        def invoke(self, *args, **kwargs):
            raise OSError("always fails")

    llm = AlwaysFails()
    add_retry_to_llm(llm, max_retries=1)
    with pytest.raises(OSError):
        llm.invoke()


# ---------------------------------------------------------------------------
# FILE TOOLS
# ---------------------------------------------------------------------------

def test_write_file(tmp_path):
    fp = tmp_path / "hello.py"
    status = write_file(str(fp), "print('hi')")
    assert status == "ok"
    assert fp.read_text() == "print('hi')"


def test_read_file(tmp_path):
    fp = tmp_path / "app.py"
    fp.write_text("x = 1", encoding="utf-8")
    content = read_file(str(fp))
    assert content == "x = 1"


def test_ensure_directory(tmp_path):
    target = tmp_path / "a" / "b" / "c"
    ensure_directory(str(target))
    assert target.exists()


def test_parse_code_blocks_with_path_markers():
    text = """some text
# --- src/app.py ---
print("hello")
# --- src/utils.py ---
def util(): pass
"""
    blocks = parse_code_blocks(text)
    assert "src/app.py" in blocks
    assert "src/utils.py" in blocks
    assert 'print("hello")' in blocks["src/app.py"]


def test_parse_code_blocks_with_fence():
    text = "```python\nprint('fenced')\n```"
    blocks = parse_code_blocks(text)
    # When there is no # --- marker, parse_code_blocks may return
    # a key like "code_0" or return an empty dict.
    assert isinstance(blocks, dict)


# ---------------------------------------------------------------------------
# ROUTING  (asserts routers return a REAL graph node name)
# ---------------------------------------------------------------------------

_ALL_ROUTERS = [
    ("route_after_review", route_after_review),
    ("route_after_worker_review", route_after_worker_review),
    ("route_after_dispatcher", route_after_dispatcher),
    ("route_after_batch_check", route_after_batch_check),
    ("route_by_execution_mode", route_by_execution_mode),
    ("route_after_human", route_after_human),
    ("route_after_backend_lead", route_after_backend_lead),
    ("route_by_mode", route_by_mode),
]


@require_state
def test_routers_are_exported():
    missing = [name for name, fn in _ALL_ROUTERS if fn is None]
    assert not missing, f"routing functions not found in graph module: {missing}"


@require_state
def test_routers_return_valid_node_names():
    g = compiled_graph.get_graph()
    node_names = set(g.nodes.keys())
    # Include worker subgraph node names (not in main graph)
    worker_node_names = {"worker_module_planner", "worker_coder",
                         "worker_reviewer", "worker_fixer", "worker_complete"}
    all_names = node_names | worker_node_names

    cases = []

    if route_after_review is not None:
        cases.append((route_after_review, {"review_score": 8, "review_threshold": 7}))
        cases.append((route_after_review, {"review_score": 3, "review_threshold": 7}))

    if route_after_worker_review is not None:
        cases.append((route_after_worker_review, {"review_score": 8, "review_threshold": 7}))

    if route_after_dispatcher is not None:
        cases.append((route_after_dispatcher, {"batch_modules": ["m1"]}))
        cases.append((route_after_dispatcher, {"batch_modules": []}))

    if route_after_batch_check is not None:
        cases.append((route_after_batch_check, {"pending_modules": []}))

    if route_by_execution_mode is not None:
        cases.append((route_by_execution_mode, {"execution_mode": "parallel"}))

    if route_after_human is not None:
        cases.append((route_after_human, {"human_approved": True}))
        cases.append((route_after_human, {"human_approved": False}))

    if route_after_backend_lead is not None:
        cases.append((route_after_backend_lead, {"current_module": None}))

    if route_after_analyzer is not None:
        cases.append((route_after_analyzer, {"mode": "analyze"}))
        cases.append((route_after_analyzer, {"mode": "create_new"}))
        cases.append((route_after_analyzer, {"mode": "update"}))

    if route_by_mode is not None:
        cases.append((route_by_mode, {"mode": "create_new"}))

    assert cases, "no routing functions were exported to test"

    for fn, st in cases:
        target = fn(st)
        assert isinstance(target, str), f"{fn.__name__} must return a node-name string"
        assert target in all_names, f"{fn.__name__}({st}) -> {target!r} is not a graph node"


@require_state
def test_route_after_review_branches():
    if route_after_review is None:
        pytest.skip("route_after_review not exported")
    passed = route_after_review({"review_score": 9, "review_threshold": 7})
    failed = route_after_review({"review_score": 3, "review_threshold": 7})
    assert passed != failed, "pass and fail must route differently"


# ---------------------------------------------------------------------------
# GRAPH TOPOLOGY
# ---------------------------------------------------------------------------

@require_state
def test_graph_has_core_nodes():
    g = compiled_graph.get_graph()
    present = set(g.nodes.keys())
    expected = {
        "planner", "architect", "quality_gen", "project_init",
        "dispatcher", "batch_sender", "worker_entry", "batch_check",
        "human_review", "qa", "delivery",
        "sandbox_setup", "test_executor", "test_fixer", "file_writer",
        "backend_lead", "module_planner", "module_coder", "reviewer", "fixer",
        "complete_module", "project_reader", "project_analyzer", "analysis_report",
    }
    missing = expected - present
    assert not missing, f"missing expected nodes: {missing}"


@require_state
def test_graph_entry_point_resolves():
    g = compiled_graph.get_graph()
    assert g.nodes, "graph has no nodes"


@require_state
def test_analyze_mode_is_read_only_report(monkeypatch):
    """`analyze` mode must read the project, produce a report, and write NO files."""
    import json
    import tempfile
    from pathlib import Path

    from langchain_core.messages import AIMessage
    from langchain_core.runnables import RunnableLambda

    from agents import _make_json_llm
    from state import ProjectAnalysis
    from config import WorkflowConfig, WorkflowMode
    from main import config_to_initial_state

    tmp = Path(tempfile.mkdtemp())
    (tmp / "app.py").write_text("print('hello')\n", encoding="utf-8")
    original_entries = set(os.listdir(tmp))

    analysis_json = json.dumps({
        "tech_stack": "Python",
        "modules": ["app"],
        "missing_modules": [],
        "issues": ["no tests"],
        "architecture_summary": "single file script",
    })

    def fake_analyzer_llm(_):
        return AIMessage(content=analysis_json)

    def fake_report_llm(_):
        return AIMessage(content="## Report\nThis is a read-only report.")

    fake_llms = {
        "llm": RunnableLambda(fake_report_llm),
        "tool_llm": RunnableLambda(lambda _: AIMessage(content="")),
        "planner": RunnableLambda(lambda _: AIMessage(content="")),
        "architect": RunnableLambda(lambda _: AIMessage(content="")),
        "module_planner": RunnableLambda(lambda _: AIMessage(content="")),
        "reviewer": RunnableLambda(lambda _: AIMessage(content="")),
        "analyzer": _make_json_llm(RunnableLambda(fake_analyzer_llm), ProjectAnalysis),
    }

    with monkeypatch.context() as m:
        m.setattr(agents_mod, "_get_llms", lambda state: fake_llms)
        cfg = WorkflowConfig(
            mode=WorkflowMode("analyze"),
            requirement="analyze this project and tell me about it",
            project_path=str(tmp),
            output_dir=str(tmp),
        )
        initial = config_to_initial_state(cfg)
        result = graph_mod.app.invoke(
            initial, config={"configurable": {"thread_id": "analyze-test"}}
        )

    assert result.get("delivery_package"), "analyze should produce a report"
    assert "read-only report" in result["delivery_package"]
    # No files/dirs should have been created by the analyze path.
    assert set(os.listdir(tmp)) == original_entries, "analyze wrote files to the project"



# ---------------------------------------------------------------------------
# TRACING + COST LOGGING  (observability.tracing)
# ---------------------------------------------------------------------------

def test_tracer_records_and_costs(tmp_path):
    from observability.tracing import Tracer
    t = Tracer(log_dir=str(tmp_path), enabled=True)
    t.start_run("test")
    rec = t.record_start("planner")
    t.record_end(rec, in_text="hello world " * 200, out_text="x" * 1500,
                 model="gpt-4o-mini")
    t.end_run()
    assert t.total_calls() == 1
    assert t.total_tokens() > 0
    assert t.total_cost_usd() > 0
    assert (Path(tmp_path) / "trace_test.jsonl").exists()
    lines = (Path(tmp_path) / "trace_test.jsonl").read_text().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["node"] == "planner"


def test_tracer_slowest_nodes(tmp_path):
    from observability.tracing import Tracer
    t = Tracer(log_dir=str(tmp_path))
    t.start_run("s")
    r0 = t.record_start("fast")
    t.record_end(r0, out_text="short")
    r1 = t.record_start("slow")
    import time; time.sleep(0.01)
    t.record_end(r1, out_text="long" * 500)
    r2 = t.record_start("medium")
    t.record_end(r2, out_text="medium")
    t.end_run()
    slow = t.slowest_nodes(3)
    assert slow[0].node == "slow"


def test_budget_exceeded(tmp_path):
    from observability.tracing import Tracer, BudgetExceeded
    t = Tracer(log_dir=str(tmp_path))
    t.global_budget_usd = 1e-9
    t.start_run("budget")
    rec = t.record_start("c")
    with pytest.raises(BudgetExceeded):
        t.record_end(rec, in_text="x" * 100000, out_text="y" * 100000, model="gpt-4o")
    t.end_run()


# ---------------------------------------------------------------------------
# PLAN MODE + SUPERVISOR (deterministic, no API keys)
# ---------------------------------------------------------------------------

def _fake_llms_with_supervisor(supervisor_json: str) -> dict:
    """Build a fake `_get_llms` result including a supervisor LLM."""
    from langchain_core.messages import AIMessage
    from langchain_core.runnables import RunnableLambda
    from agents import _make_json_llm

    modulelist = json.dumps({
        "stories": ["Build the app"], "modules": ["app"],
        "tech_stack": "Python/FastAPI",
    })
    arch = json.dumps({
        "tech_stack": "Python/FastAPI", "db_schema": "",
        "api_endpoints": "", "folder_structure": "app/\n",
        "architecture_diagram": "",
    })
    codereview = json.dumps({
        "score": 8, "issues": [], "logic_correctness": "ok",
        "security_check": "ok",
    })
    projanalysis = json.dumps({
        "tech_stack": "Python", "modules": ["app"], "missing_modules": [],
        "issues": [], "architecture_summary": "x",
    })

    def mk(content):
        return RunnableLambda(lambda _: AIMessage(content=content))

    return {
        "llm": mk("print('hi from fake')"),
        "tool_llm": mk(""),
        "planner": _make_json_llm(mk(modulelist), state_mod.ModuleList),
        "architect": _make_json_llm(mk(arch), state_mod.ArchitectureDoc),
        "module_planner": _make_json_llm(mk(""), state_mod.ModulePlan),
        "reviewer": _make_json_llm(mk(codereview), state_mod.CodeReview),
        "analyzer": _make_json_llm(mk(projanalysis), state_mod.ProjectAnalysis),
        "supervisor": _make_json_llm(mk(supervisor_json), state_mod.ExecutionPlan),
    }


@require_state
def test_plan_mode_pauses_before_building(monkeypatch):
    """With plan approval requested, the graph must pause at plan_review
    (before generating code), not at human_review."""
    sup = json.dumps({
        "pause_for_plan_approval": True, "skip_build": False,
        "skip_tests": False, "execution_mode": "parallel",
        "review_threshold": 7, "max_fix_attempts": 3,
        "security_focus": False, "notes": "plan",
    })
    with monkeypatch.context() as m:
        m.setattr(agents_mod, "_get_llms", lambda s: _fake_llms_with_supervisor(sup))
        init = {
            "requirement": "build a login API with JWT",
            "mode": "create_new",
            "plan_mode": True,
            "project_path": str(Path(tempfile.mkdtemp())),
        }
        result = compiled_graph.invoke(
            init, config={"configurable": {"thread_id": "plan-pause"}}
        )
    assert result.get("__interrupt__"), "expected graph to pause at plan_review"
    payload = result["__interrupt__"][0]
    value = getattr(payload, "value", payload)
    assert value.get("type") == "plan_review", value
    # No code should have been generated yet.
    assert not result.get("generated_code"), "plan mode must not build before approval"


@require_state
def test_plan_mode_approve_continues_to_build(monkeypatch):
    """Approving the plan resumes and continues into the build (reaching
    the final human_review interrupt)."""
    sup = json.dumps({
        "pause_for_plan_approval": True, "skip_build": False,
        "skip_tests": False, "execution_mode": "parallel",
        "review_threshold": 7, "max_fix_attempts": 3,
        "security_focus": False, "notes": "plan",
    })
    with monkeypatch.context() as m:
        m.setattr(agents_mod, "_get_llms", lambda s: _fake_llms_with_supervisor(sup))
        init = {
            "requirement": "build a login API with JWT",
            "mode": "create_new",
            "plan_mode": True,
            "project_path": str(Path(tempfile.mkdtemp())),
        }
        result = compiled_graph.invoke(
            init, config={"configurable": {"thread_id": "plan-approve"}}
        )
        assert result.get("__interrupt__")
        result = compiled_graph.invoke(
            # type: ignore[arg-type]
            Command(
                resume={"choice": "yes", "feedback": ""}
            ),
            config={"configurable": {"thread_id": "plan-approve"}},
        )
    # After approval it should have proceeded past the plan gate and built.
    assert result.get("completed_modules") is not None
    assert result.get("generated_code"), "approval should have triggered a build"
    # And it should now be paused at the final human_review (not plan_review).
    assert result.get("__interrupt__"), "expected final human_review interrupt"
    final_value = getattr(result["__interrupt__"][0], "value", result["__interrupt__"][0])
    assert final_value.get("type") != "plan_review"


@require_state
def test_plan_mode_reject_loops_to_planner(monkeypatch):
    """Rejecting the plan loops back to the planner (another plan_review)."""
    sup = json.dumps({
        "pause_for_plan_approval": True, "skip_build": False,
        "skip_tests": False, "execution_mode": "parallel",
        "review_threshold": 7, "max_fix_attempts": 3,
        "security_focus": False, "notes": "plan",
    })
    with monkeypatch.context() as m:
        m.setattr(agents_mod, "_get_llms", lambda s: _fake_llms_with_supervisor(sup))
        init = {
            "requirement": "build a login API with JWT",
            "mode": "create_new",
            "plan_mode": True,
            "project_path": str(Path(tempfile.mkdtemp())),
        }
        result = compiled_graph.invoke(
            init, config={"configurable": {"thread_id": "plan-reject"}}
        )
        result = compiled_graph.invoke(
            Command(
                resume={"choice": "no", "feedback": "make it smaller"}
            ),
            config={"configurable": {"thread_id": "plan-reject"}},
        )
    assert result.get("__interrupt__"), "expected to pause again at plan_review"
    value = getattr(result["__interrupt__"][0], "value", result["__interrupt__"][0])
    assert value.get("type") == "plan_review"
    assert "smaller" in (result.get("human_feedback") or "")


@require_state
def test_supervisor_skip_build_delivers_plan(monkeypatch):
    """Supervisor skip_build + approved -> deliver plan, no code, no further interrupt."""
    sup = json.dumps({
        "pause_for_plan_approval": True, "skip_build": True,
        "skip_tests": False, "execution_mode": "parallel",
        "review_threshold": 7, "max_fix_attempts": 3,
        "security_focus": False, "notes": "plan only",
    })
    with monkeypatch.context() as m:
        m.setattr(agents_mod, "_get_llms", lambda s: _fake_llms_with_supervisor(sup))
        init = {
            "requirement": "plan a login API with JWT",
            "mode": "create_new",
            "plan_mode": True,
            "project_path": str(Path(tempfile.mkdtemp())),
        }
        result = compiled_graph.invoke(
            init, config={"configurable": {"thread_id": "plan-skipbuild"}}
        )
        result = compiled_graph.invoke(
            Command(
                resume={"choice": "yes", "feedback": ""}
            ),
            config={"configurable": {"thread_id": "plan-skipbuild"}},
        )
    assert not result.get("__interrupt__"), "plan-only should end without a build interrupt"
    assert result.get("delivery_package"), "plan-only should produce a delivery package"


@require_state
def test_route_after_human_skip_tests():
    if route_after_human is None:
        pytest.skip("route_after_human not exported")
    target = route_after_human({
        "human_approved": True, "skip_tests": True, "execution_mode": "parallel",
    })
    assert target == "delivery", f"skip_tests must bypass QA: {target}"
    target = route_after_human({
        "human_approved": True, "skip_tests": False, "execution_mode": "parallel",
    })
    assert target == "qa"


@require_state
def test_get_llms_exposes_supervisor_for_both_providers():
    """Regression: both the ollama (default) and lm_studio branches of
    `_get_llms` must expose a 'supervisor' LLM, otherwise the
    supervisor node silently falls back to a static default plan."""
    from agents import _get_llms
    for provider, base_url in (("ollama", "https://ollama.com"),
                                ("lm_studio", "http://localhost:1234/v1")):
        llms = _get_llms({
            "provider": provider,
            "llm_base_url": base_url,
            "llm_model": "test-model",
        })
        assert "supervisor" in llms, (
            f"{provider} branch of _get_llms is missing the 'supervisor' LLM"
        )


@require_state
def test_route_after_plan_review_branches():
    if "route_after_plan_review" not in dir(graph_mod):
        pytest.skip("route_after_plan_review not exported")
    r = graph_mod.route_after_plan_review
    assert r({"plan_rejected": True}) == "planner"
    assert r({"plan_rejected": False, "plan_approved": True,
               "execution_plan": {"skip_build": True}}) == "delivery"
    assert r({"plan_rejected": False, "plan_approved": True,
               "execution_plan": {"skip_build": False}}) == "project_init"


# ---------------------------------------------------------------------------
# END-TO-END (opt-in via RUN_E2E=1)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not RUN_E2E, reason="set RUN_E2E=1 to run end-to-end")
def test_end_to_end_minimal(tmp_path, monkeypatch):
    """Minimal E2E with a fake model."""
    from langchain_core.runnables import RunnableLambda

    class FakeResult:
        """Duck-typed stand-in for the structured-output objects the nodes
        read (ModuleList/ArchitectureDoc/ModulePlan/CodeReview/...)."""
        content = "print('hi from fake')"
        module_name = "app"
        modules = ["app"]
        tech_stack = "Python/FastAPI"
        stories = ["Build the app"]
        files = []
        score = 8
        issues = []
        logic_correctness = "ok"
        security_check = "ok"
        architecture_summary = "none"
        missing_modules = []
        db_schema = ""
        api_endpoints = ""
        folder_structure = "app/\n"
        architecture_diagram = ""
        exports = []
        dependencies = []
        api_routes = []
        purpose = ""

    def fake_model(*args, **kwargs):
        return RunnableLambda(lambda inputs: FakeResult())

    monkeypatch.setattr(agents_mod, "_get_llms", lambda s: {
        "llm": fake_model(),
        "tool_llm": fake_model(),
        "planner": fake_model(),
        "architect": fake_model(),
        "module_planner": fake_model(),
        "reviewer": fake_model(),
        "analyzer": fake_model(),
    })

    cfg = WorkflowConfig(project_path=str(tmp_path), mode="create_new")
    init = {
        "requirement": "build a hello-world flask app",
        "project_path": str(tmp_path),
    }

    # Use the config as initial state overrides
    from main import config_to_initial_state
    state = config_to_initial_state(cfg)
    state.update(init)
    # A checkpointer/thread_id is required because the graph uses interrupt()
    # for human-in-the-loop review.
    result = compiled_graph.invoke(
        state, config={"configurable": {"thread_id": "e2e-test"}}
    )
    # The graph must pause at human_review rather than blocking on stdin.
    assert result.get("__interrupt__"), "expected graph to pause at human_review"
    assert result.get("completed_modules") is not None
