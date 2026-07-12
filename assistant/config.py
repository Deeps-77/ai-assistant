"""Configuration and model resolution for the interactive delivery assistant.

The assistant targets two runtime profiles:

* ``ollama`` -> remote/cloud Ollama endpoint, model ``gemma4:31b-cloud``
* ``local``  -> LM Studio's OpenAI-compatible API (default ``http://localhost:1234/v1``),
  model ``qwen/qwen3-4b`` (or ``google/gemma-4-e4b``)

The orchestrator (the deep agent) and the wrapped delivery pipeline can use
different providers: the orchestrator talks to any ``init_chat_model`` provider
(e.g. ``openai`` for LM Studio), while the delivery pipeline only understands
``ollama`` / ``lm_studio``. They are configured independently below.

Everything is overridable through environment variables so the assistant can be
re-pointed at any OpenAI-compatible or Ollama tool-calling model.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

PROFILES: dict[str, dict[str, str]] = {
    "ollama": {
        "provider": "ollama",            # orchestrator provider (init_chat_model)
        "delivery_provider": "ollama",  # provider passed to the delivery pipeline
        "model": "gemma4:31b-cloud",
        "delivery_model": "gemma4:31b-cloud",
        "base_url_env": "OLLAMA_BASE_URL",
        "base_url_default": "http://localhost:11434",
        "api_key": "",
        "ctx_size_default": "32768",
    },
    "local": {
        # LM Studio exposes an OpenAI-compatible API.
        "provider": "openai",
        "delivery_provider": "lm_studio",
        "model": "qwen/qwen3-4b",
        "delivery_model": "qwen/qwen3-4b",
        "base_url_env": "LMSTUDIO_BASE_URL",
        "base_url_default": "http://localhost:1234/v1",
        "api_key": "lm-studio",
        "ctx_size_default": "",
    },
}


@dataclass
class AssistantConfig:
    profile: str = "ollama"

    # Orchestrator (deep agent) model
    provider: str = "ollama"
    model: str = "gemma4:31b-cloud"
    base_url: Optional[str] = None
    api_key: Optional[str] = None

    # Optional generation tuning (None -> use the endpoint's defaults)
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None

    # Context window (Ollama sets `num_ctx`; LM Studio/OpenAI is server-controlled)
    ctx_size: Optional[int] = None
    delivery_ctx_size: Optional[int] = None

    # Delivery pipeline model (uses the pipeline's own provider names)
    delivery_provider: str = "ollama"
    delivery_model: Optional[str] = None
    delivery_base_url: Optional[str] = None
    delivery_api_key: Optional[str] = None

    project_path: str = field(default_factory=os.getcwd)
    tech_stack: Optional[str] = None
    execution_mode: str = "parallel"
    sandbox_enabled: bool = False
    interrupt_shell: bool = True
    plan_mode: bool = False                     # opencode-style: pause for plan approval

    @property
    def memory_path(self) -> str:
        return os.path.join(self.project_path, ".assistant", "memory.json")


def resolve_assistant_config(project_path: Optional[str] = None) -> AssistantConfig:
    profile = os.getenv("ASSISTANT_PROFILE", "ollama").strip().lower()
    if profile not in PROFILES:
        profile = "ollama"
    base = PROFILES[profile]

    provider = os.getenv("ASSISTANT_PROVIDER", base["provider"]).strip()
    delivery_provider = os.getenv("ASSISTANT_DELIVERY_PROVIDER", base["delivery_provider"]).strip()
    model = os.getenv("ASSISTANT_MODEL", base["model"]).strip()
    delivery_model = os.getenv(
        "DELIVERY_MODEL", os.getenv("ASSISTANT_DELIVERY_MODEL", model)
    ).strip()

    base_url = os.getenv(
        "ASSISTANT_BASE_URL", os.getenv(base["base_url_env"], base["base_url_default"])
    ) or None
    delivery_base_url = os.getenv(
        "DELIVERY_BASE_URL", os.getenv("ASSISTANT_DELIVERY_BASE_URL", base_url)
    ) or None

    api_key = os.getenv("ASSISTANT_API_KEY", base["api_key"]) or None
    delivery_api_key = os.getenv("ASSISTANT_DELIVERY_API_KEY", api_key) or None

    max_tokens_raw = os.getenv("ASSISTANT_MAX_TOKENS")
    max_tokens = int(max_tokens_raw) if max_tokens_raw else None
    temp_raw = os.getenv("ASSISTANT_TEMPERATURE")
    temperature = float(temp_raw) if temp_raw else None

    ctx_raw = os.getenv("ASSISTANT_CTX_SIZE", base.get("ctx_size_default") or "")
    ctx_size = int(ctx_raw) if ctx_raw else None
    delivery_ctx_raw = os.getenv("DELIVERY_CTX_SIZE", os.getenv("ASSISTANT_DELIVERY_CTX_SIZE", ctx_raw))
    delivery_ctx_size = int(delivery_ctx_raw) if delivery_ctx_raw else None

    root = project_path or os.getenv("ASSISTANT_PROJECT_PATH") or os.getcwd()
    root = os.path.abspath(root)

    return AssistantConfig(
        profile=profile,
        provider=provider,
        delivery_provider=delivery_provider,
        model=model,
        delivery_model=delivery_model,
        base_url=base_url,
        delivery_base_url=delivery_base_url,
        api_key=api_key,
        delivery_api_key=delivery_api_key,
        max_tokens=max_tokens,
        temperature=temperature,
        ctx_size=ctx_size,
        delivery_ctx_size=delivery_ctx_size,
        project_path=root,
        tech_stack=os.getenv("ASSISTANT_TECH_STACK") or None,
        execution_mode=os.getenv("ASSISTANT_EXECUTION_MODE", "parallel").strip(),
        sandbox_enabled=os.getenv("ASSISTANT_SANDBOX", "0") == "1",
        interrupt_shell=os.getenv("ASSISTANT_INTERRUPT_SHELL", "1") == "1",
        plan_mode=os.getenv("ASSISTANT_PLAN_MODE", "0") == "1",
    )


def build_chat_model(
    provider: str,
    model: str,
    base_url: Optional[str],
    api_key: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    ctx_size: Optional[int] = None,
):
    """Construct a tool-calling chat model for the orchestrator.

    The provider is passed explicitly (via ``model_provider``) rather than as a
    ``provider:model`` shorthand, because Ollama model tags themselves contain a
    colon (e.g. ``gemma4:31b-cloud``) which the shorthand parser would mangle.

    For Ollama, ``ctx_size`` is forwarded as ``num_ctx`` so the model's context
    window is large enough to hold the (sizeable) deep-agent system prompt.
    """
    from langchain.chat_models import init_chat_model

    kwargs: dict = {}
    if base_url:
        kwargs["base_url"] = base_url
    if api_key:
        kwargs["api_key"] = api_key
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if temperature is not None:
        kwargs["temperature"] = temperature
    if provider == "ollama" and ctx_size:
        kwargs["num_ctx"] = ctx_size
    return init_chat_model(model=model, model_provider=provider, **kwargs)
