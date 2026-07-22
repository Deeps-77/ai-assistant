"""
DevSwarm Configuration
Loads settings from .env and exposes a singleton Settings object.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Resolve .env relative to repo root (two levels up from this file)
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=_ENV_PATH, override=False)


@dataclass
class Settings:
    # Ollama / LLM
    ollama_model: str = field(
        default_factory=lambda: os.getenv("OLLAMA_MODEL", "gemma4:31b-cloud")
    )
    ollama_api_key: str = field(
        default_factory=lambda: os.getenv("OLLAMA_API_KEY", "")
    )
    ollama_base_url: str = field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "https://ollama.com")
    )
    ollama_num_ctx: int = field(
        default_factory=lambda: int(os.getenv("OLLAMA_NUM_CTX", "32768"))
    )
    ollama_num_predict: int = field(
        default_factory=lambda: int(os.getenv("OLLAMA_NUM_PREDICT", "4096"))
    )

    # Workspace
    workspaces_root: Path = field(
        default_factory=lambda: Path(
            os.getenv("DEVSWARM_WORKSPACES_ROOT", "workspaces")
        )
    )

    # HITL
    hitl_checkpoints: list[str] = field(
        default_factory=lambda: [
            "after_plan",       # always: approve plan before build
            "before_file_write",  # optional
            "before_shell_exec",  # optional
        ]
    )

    # Agent limits
    max_tool_calls: int = field(
        default_factory=lambda: int(os.getenv("DEVSWARM_MAX_TOOL_CALLS", "50"))
    )
    max_agent_iterations: int = field(
        default_factory=lambda: int(os.getenv("DEVSWARM_MAX_ITERATIONS", "20"))
    )
    max_review_attempts: int = field(
        default_factory=lambda: int(os.getenv("DEVSWARM_MAX_REVIEW_ATTEMPTS", "3"))
    )

    # LangGraph
    recursion_limit: int = 100

    def workspace_for(self, session_id: str) -> Path:
        """Return (and create) a dedicated workspace directory for a session."""
        ws = self.workspaces_root / session_id
        ws.mkdir(parents=True, exist_ok=True)
        return ws


# Singleton
settings = Settings()
