import os
import json
import uuid
import argparse
from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field


class WorkflowMode(str, Enum):
    CREATE_NEW = "create_new"
    ANALYZE = "analyze"
    UPDATE = "update"


class WorkflowConfig(BaseModel):
    thread_id: str = Field(default_factory=lambda: f"wf-{uuid.uuid4().hex[:8]}")
    mode: WorkflowMode = WorkflowMode.CREATE_NEW

    requirement: str = ""
    project_path: Optional[str] = None
    tech_stack: Optional[str] = None
    output_dir: str = "outputs"

    max_fix_attempts: int = 3
    review_threshold: int = 7
    recursion_limit: int = 150

    provider: str = Field(default_factory=lambda: os.getenv("LLM_PROVIDER", "ollama"))
    llm_model: str = Field(default_factory=lambda: os.getenv("LLM_MODEL", "gemma3:12b-cloud"))
    llm_base_url: str = Field(default_factory=lambda: os.getenv(
        "LLM_BASE_URL",
        os.getenv("OLLAMA_BASE_URL", "https://ollama.com"),
    ))

    @classmethod
    def from_yaml(cls, path: str) -> "WorkflowConfig":
        import yaml
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        data.pop("mode", None)
        return cls(mode=WorkflowMode(data["mode"]), **{k: v for k, v in data.items() if k != "mode"})

    @classmethod
    def from_json(cls, path: str) -> "WorkflowConfig":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls(mode=WorkflowMode(data["mode"]), **{k: v for k, v in data.items() if k != "mode"})

    @classmethod
    def from_cli(cls, argv: list[str]) -> "WorkflowConfig":
        parser = argparse.ArgumentParser(description="AI Software Delivery Team")
        parser.add_argument("--config", help="Path to YAML/JSON config file (overlaid by CLI flags)")
        parser.add_argument("--mode", choices=[m.value for m in WorkflowMode], help="Workflow mode")
        parser.add_argument("--requirement", help="Software requirement description")
        parser.add_argument("--project-path", help="Path to existing or target project")
        parser.add_argument("--tech-stack", help='Tech stack (e.g. "Python/FastAPI", "Rust/Axum")')
        parser.add_argument("--output-dir", default="outputs", help="Output directory")
        parser.add_argument("--max-fix-attempts", type=int, help="Max review-fix cycles per module")
        parser.add_argument("--review-threshold", type=int, help="Minimum score to pass review (1-10)")
        parser.add_argument("--recursion-limit", type=int, help="LangGraph recursion limit")
        parser.add_argument("--provider", choices=["ollama", "lm_studio"], help="LLM provider")
        parser.add_argument("--llm-model", help="Model name")
        parser.add_argument("--llm-base-url", help="LLM API base URL")
        args = parser.parse_args(argv[1:])

        if args.config:
            if args.config.endswith((".yaml", ".yml")):
                cfg = cls.from_yaml(args.config)
            else:
                cfg = cls.from_json(args.config)
        else:
            cfg = cls()

        overrides = {k.replace("-", "_"): v for k, v in vars(args).items()
                     if v is not None and k != "config"}
        for key, val in overrides.items():
            if key == "mode":
                val = WorkflowMode(val)
            setattr(cfg, key, val)

        return cfg
