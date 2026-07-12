"""Tests for the assistant wiring (no API keys, no model calls)."""

import asyncio

from langgraph.store.base import GetOp, PutOp

from langchain_ollama import ChatOllama

from assistant.config import AssistantConfig, build_chat_model, resolve_assistant_config
from assistant.app import build_assistant
from assistant.store import JsonFileStore


def test_resolve_config_local_profile(monkeypatch):
    monkeypatch.setenv("ASSISTANT_PROFILE", "local")
    cfg = resolve_assistant_config("/tmp/x")
    assert cfg.profile == "local"
    assert cfg.model == "qwen/qwen3-4b"
    # Local profile uses LM Studio's OpenAI-compatible API for the orchestrator
    # and the pipeline's own "lm_studio" provider for delivery.
    assert cfg.provider == "openai"
    assert cfg.delivery_provider == "lm_studio"
    assert cfg.base_url == "http://localhost:1234/v1"
    assert cfg.api_key == "lm-studio"


def test_resolve_config_overrides(monkeypatch):
    monkeypatch.setenv("ASSISTANT_PROFILE", "local")
    monkeypatch.setenv("ASSISTANT_MODEL", "google/gemma-4-e4b")
    monkeypatch.setenv("ASSISTANT_BASE_URL", "http://127.0.0.1:11434")
    cfg = resolve_assistant_config()
    assert cfg.model == "google/gemma-4-e4b"
    assert cfg.base_url == "http://127.0.0.1:11434"


def test_build_chat_model(monkeypatch):
    monkeypatch.setenv("ASSISTANT_PROFILE", "ollama")
    cfg = resolve_assistant_config()
    model = build_chat_model(cfg.provider, cfg.model, cfg.base_url)
    assert model is not None


def test_build_chat_model_ollama_sets_num_ctx(monkeypatch):
    monkeypatch.setenv("ASSISTANT_PROFILE", "ollama")
    cfg = resolve_assistant_config()
    model = build_chat_model(
        cfg.provider, cfg.model, cfg.base_url, cfg.api_key, None, None, cfg.ctx_size
    )
    assert type(model).__name__ == "ChatOllama"
    assert getattr(model, "num_ctx", None) == 32768


def test_resolve_config_ctx_size(monkeypatch):
    monkeypatch.setenv("ASSISTANT_PROFILE", "ollama")
    monkeypatch.setenv("ASSISTANT_CTX_SIZE", "16384")
    cfg = resolve_assistant_config()
    assert cfg.ctx_size == 16384
    # delivery inherits from the orchestrator default when not overridden
    assert cfg.delivery_ctx_size == 16384


def test_resolve_config_local_has_no_ctx_default(monkeypatch):
    monkeypatch.setenv("ASSISTANT_PROFILE", "local")
    cfg = resolve_assistant_config()
    assert cfg.ctx_size is None


def test_build_assistant_no_api_key(monkeypatch, tmp_path):
    monkeypatch.setenv("ASSISTANT_PROJECT_PATH", str(tmp_path))
    cfg = resolve_assistant_config(str(tmp_path))
    agent = build_assistant(cfg=cfg)
    assert agent is not None


def test_json_store_persists_across_reload(tmp_path):
    path = str(tmp_path / "mem.json")
    store = JsonFileStore(path)
    store.batch([
        PutOp(namespace=("projectMemory",), key="profile", value={"stack": "python"}, index=None, ttl=None)
    ])
    got = store.batch([GetOp(namespace=("projectMemory",), key="profile", refresh_ttl=False)])
    assert got[0] is not None
    assert got[0].value["stack"] == "python"

    reloaded = JsonFileStore(path)
    got2 = reloaded.batch([GetOp(namespace=("projectMemory",), key="profile", refresh_ttl=False)])
    assert got2[0].value["stack"] == "python"


def test_get_llms_honors_ctx_size(monkeypatch):
    """The delivery pipeline's `_get_llms` must forward `ctx_size` as num_ctx."""
    import agents as agents_mod

    captured = {}

    def fake_chat_ollama(**kwargs):
        captured.update(kwargs)
        # minimal stand-in so add_retry_to_llm / with_structured_output work
        from langchain_core.messages import AIMessage

        class _M:
            def __init__(self, **kw):
                self.__dict__.update(kw)
            def invoke(self, *a, **k):
                return AIMessage(content="")
            def bind_tools(self, tools):
                return self
            def with_structured_output(self, schema, method=None):
                return self
        return _M(**kwargs)

    monkeypatch.setattr("langchain_ollama.ChatOllama", fake_chat_ollama)

    llms = agents_mod._get_llms({
        "provider": "ollama",
        "llm_base_url": "http://localhost:11434",
        "llm_model": "gemma4:31b-cloud",
        "max_retries": 2,
        "ctx_size": 32768,
    })
    assert captured.get("num_ctx") == 32768
    assert llms["llm"] is not None
