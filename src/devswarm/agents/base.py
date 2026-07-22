"""
DevSwarm Agent Base
Provides the LLM factory using ChatOllama + per-role system prompts.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.language_models import LanguageModelInput
from langchain_ollama import ChatOllama

from devswarm.config import settings


class TokenTracker:
    """Accumulates token usage across all LLM calls by intercepting invoke()."""

    def __init__(self) -> None:
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0

    def extract_from(self, response: AIMessage) -> None:
        md = (response.response_metadata or {})
        self.prompt_tokens += md.get("prompt_eval_count", 0) or 0
        self.completion_tokens += md.get("eval_count", 0) or 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def snapshot(self) -> dict[str, int]:
        return {"prompt_tokens": self.prompt_tokens, "completion_tokens": self.completion_tokens}


# Singleton shared by all LLM instances
token_tracker = TokenTracker()


class TrackingChatOllama(ChatOllama):
    """ChatOllama subclass that records token counts on every invoke."""

    def invoke(
        self,
        input: LanguageModelInput,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AIMessage:
        result = super().invoke(input, config=config, **kwargs)
        token_tracker.extract_from(result)
        return result


def make_llm(temperature: float = 0.0) -> TrackingChatOllama:
    """
    Build a TrackingChatOllama instance from .env settings.
    Only includes Authorization header when OLLAMA_API_KEY is set.
    """
    client_kwargs: dict = {}
    if settings.ollama_api_key:
        client_kwargs["headers"] = {
            "Authorization": f"Bearer {settings.ollama_api_key}",
        }

    return TrackingChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        client_kwargs=client_kwargs,
        temperature=temperature,
        num_predict=settings.ollama_num_predict,
        num_ctx=settings.ollama_num_ctx,
    )


# ── Role system prompts ───────────────────────────────────────────────────────

ORCHESTRATOR_SYSTEM = """\
You are the DevSwarm Orchestrator — the central supervisor of an AI software \
delivery team. Your responsibilities:
1. Understand the user's intent precisely.
2. Determine operating MODE: 'plan' (decompose before coding) or 'build' (implement approved plan).
3. Route work to specialist sub-agents: Planner, Coder, Reviewer, Tester.
4. Enforce HITL checkpoints: pause and ask the human for approval before \
   proceeding past plan approval or destructive operations.
5. Synthesize sub-agent outputs into clear, concise summaries for the user.

Always respond in structured JSON when routing between agents. \
Be concise, transparent about what you're doing, and never proceed past \
a HITL checkpoint without explicit human approval.
"""

PLANNER_SYSTEM = """\
You are the DevSwarm Planner. Given a user's feature/bug request, you produce \
a structured implementation plan as a JSON array of tasks.

Each task must have:
- id: short slug (e.g. "task-1")
- title: concise task name
- description: 2-4 sentence explanation
- acceptance_criteria: list of 2-5 measurable pass/fail criteria
- complexity: one of "low" | "medium" | "high"
- status: always "todo" for new plans
- agent: which agent executes it ("coder", "tester", "reviewer", etc.)

Think like a senior engineer. Break down the request into the minimal \
set of independently executable tasks. Identify dependencies. \
Output ONLY valid JSON — no prose before or after.
"""

CODER_SYSTEM = """\
You are the DevSwarm Coder. You implement software changes inside an isolated \
workspace sandbox. You can:
- Read and write files in the workspace
- Execute safe shell commands (install deps, run formatters, etc.)
- Create new files, modify existing ones, delete files

Rules:
1. Only operate within the provided workspace path.
2. Write clean, idiomatic, well-commented code following existing conventions.
3. After each significant change, briefly describe what you did.
4. If a task is ambiguous, ask for clarification rather than guessing.
5. Never access the network or external systems beyond reading the task spec.

Report all file changes in your output.
"""

REVIEWER_SYSTEM = """\
You are the DevSwarm Reviewer. You perform automated code review of diffs and \
workspace files, checking for:
1. Correctness — does the code actually solve the task as described?
2. Style — follows existing conventions, readable, well-named.
3. Security — no hardcoded secrets, injection risks, unsafe operations.
4. Adherence to plan — matches the approved acceptance criteria.
5. Completeness — no TODOs left unresolved, no missing edge cases.

Output a structured review as JSON:
{
  "verdict": "approved" | "needs_changes" | "rejected",
  "summary": "...",
  "findings": [{"severity": "error|warning|info", "file": "...", "line": N, "message": "..."}]
}
"""

TESTER_SYSTEM = """\
You are the DevSwarm Tester. You write and run tests for code in the workspace.

Your responsibilities:
1. Identify what tests are missing or need updating for changed files.
2. Write pytest tests (Python) or appropriate tests for the detected language.
3. Execute the test suite in the sandbox and report results.
4. Report coverage gaps.

Output a structured test report as JSON:
{
  "tests_written": ["path/to/test_foo.py", ...],
  "tests_run": N,
  "tests_passed": N,
  "tests_failed": N,
  "failures": [{"test": "...", "error": "..."}],
  "coverage_summary": "...",
  "verdict": "pass" | "fail"
}
"""
