"""Builds the interactive delivery assistant on top of ``deepagents``.

The assistant is a ``create_deep_agent`` graph: it keeps its own planning /
filesystem / shell tools for lightweight in-repo work, and delegates heavy
multi-file delivery to the wrapped :mod:`graph` pipeline through the
``software_delivery`` sub-agent.
"""

from __future__ import annotations

import os

from deepagents import create_deep_agent
from deepagents.backends.filesystem import FilesystemBackend
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver

from assistant.config import AssistantConfig, build_chat_model, resolve_assistant_config
from assistant.delivery_adapter import build_delivery_subagent
from assistant.prompts import ASSISTANT_SYSTEM_PROMPT
from assistant.store import JsonFileStore

SKILL_DIR = os.path.join(os.path.dirname(__file__), "skills")


def _skill_paths() -> list[str]:
    paths = []
    for name in ("onboard_project", "run_tests"):
        skill_dir = os.path.join(SKILL_DIR, name)
        if os.path.isdir(skill_dir):
            paths.append(skill_dir)
    return paths


def build_assistant(
    project_path: str | None = None,
    cfg: AssistantConfig | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
):
    cfg = cfg or resolve_assistant_config(project_path)

    # A checkpointer is required for human-in-the-loop interrupts (shell approval
    # and opencode-style plan review) to pause and resume. Callers that need to
    # resume across separate ``build_assistant`` calls (e.g. the HTTP server's
    # ``/run`` then ``/resume``) must pass a *shared* checkpointer instance.
    if checkpointer is None:
        checkpointer = InMemorySaver()

    model = build_chat_model(
        cfg.provider, cfg.model, cfg.base_url, cfg.api_key,
        cfg.max_tokens, cfg.temperature, cfg.ctx_size,
    )
    delivery_subagent = build_delivery_subagent(cfg)

    backend = FilesystemBackend(root_dir=cfg.project_path, virtual_mode=False)

    store = JsonFileStore(cfg.memory_path)

    interrupt_on = {"shell": cfg.interrupt_shell} if cfg.interrupt_shell else None

    agent = create_deep_agent(
        model=model,
        system_prompt=ASSISTANT_SYSTEM_PROMPT,
        subagents=[delivery_subagent],
        backend=backend,
        store=store,
        memory=["projectMemory"],
        skills=_skill_paths(),
        interrupt_on=interrupt_on,
        checkpointer=checkpointer,
        name="software_delivery_assistant",
    )
    return agent
