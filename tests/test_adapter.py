"""Tests for the delivery adapter (no API keys, no model calls)."""

import types

from assistant.delivery_adapter import (
    build_delivery_subagent,
    detect_mode,
    _summarize,
)
from langgraph.graph.state import CompiledStateGraph


def test_detect_mode_create():
    assert detect_mode("build me a todo app", project_exists=False) == "create_new"
    assert detect_mode("create a new API", project_exists=True) == "create_new"


def test_detect_mode_analyze_requires_repo():
    # analyze with no repo falls back to create_new/update
    assert detect_mode("analyze this codebase", project_exists=False) != "analyze"
    assert detect_mode("review the architecture", project_exists=True) == "analyze"


def test_detect_mode_update():
    assert detect_mode("add authentication to the project", project_exists=True) == "update"


def test_detect_mode_analyze_phrasing():
    # Q&A / report phrasing should map to read-only analyze mode
    for text in (
        "tell me about this repository",
        "explain what this project does",
        "summarize the architecture",
        "walk me through the codebase",
        "describe the main modules",
        "what does this project do",
    ):
        assert detect_mode(text, project_exists=True) == "analyze"


def test_summarize_analyze_returns_report():
    out = _summarize({"delivery_package": "## Report\nNice repo."}, "analyze")
    assert "Report" in out
    assert "Modules completed" not in out


def test_build_delivery_subagent_compiles():
    sub = build_delivery_subagent(_fake_cfg())
    assert isinstance(sub, dict)
    assert sub["name"] == "software_delivery"
    assert isinstance(sub["runnable"], CompiledStateGraph)


def test_run_delivery_invokes_graph_and_summarizes(monkeypatch):
    captured = {}

    class FakeSnapshot:
        next = ()
        values = {}
        interrupts = ()

    class FakeApp:
        def get_state(self, config=None):
            return FakeSnapshot()

        def invoke(self, state, config=None):
            captured["state"] = state
            captured["config"] = config
            return {
                "completed_modules": ["auth", "users"],
                "written_files": {"auth.py": "ok", "users.py": "ok"},
                "test_results": {"auth": {"success": True}, "users": {"success": False}},
                "delivery_package": "Shipped.",
            }

    monkeypatch.setattr("assistant.delivery_adapter.app", FakeApp())

    monkeypatch.setattr(
        "assistant.delivery_adapter.config_to_initial_state",
        lambda cfg: {
            "requirement": cfg.requirement,
            "project_path": cfg.project_path,
            "mode": cfg.mode.value,
        },
    )

    sub = build_delivery_subagent(_fake_cfg())
    result = sub["runnable"].invoke({"messages": [("user", "build a todo app")]})

    assert captured["state"]["requirement"] == "build a todo app"
    assert captured["config"]["configurable"]["thread_id"]
    msg = result["messages"][-1]
    assert "Modules completed" in msg.content
    assert "auth" in msg.content


def test_summarize_handles_empty():
    out = _summarize({}, "create_new")
    assert "Delivery complete" in out


def _fake_cfg():
    from assistant.config import AssistantConfig

    return AssistantConfig(
        provider="ollama",
        model="gemma4:31b-cloud",
        base_url="http://localhost:11434",
        delivery_model="gemma4:31b-cloud",
        delivery_base_url="http://localhost:11434",
        project_path="/tmp/proj",
    )
