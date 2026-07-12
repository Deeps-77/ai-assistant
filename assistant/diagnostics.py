"""Lightweight LangChain callback that records the last model response's
finish reason and token usage, so the REPL can report the *actual* cause of an
empty generation instead of guessing (e.g. context truncation vs. a model that
simply returned nothing).
"""

from __future__ import annotations

from langchain_core.callbacks import BaseCallbackHandler


class ModelDiagHandler(BaseCallbackHandler):
    def __init__(self) -> None:
        self.last: dict = {}

    def on_llm_end(self, response, **kwargs) -> None:
        try:
            generations = response.generations
            if not generations or not generations[0]:
                return
            msg = generations[0][0].message
            meta = getattr(msg, "response_metadata", {}) or {}
        except Exception:
            return

        done_reason = meta.get("done_reason") or meta.get("finish_reason")
        prompt_tokens = meta.get("prompt_eval_count")
        completion_tokens = meta.get("eval_count")

        # Fall back to top-level llm_output usage if present.
        llm_output = getattr(response, "llm_output", None) or {}
        usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
        if prompt_tokens is None:
            prompt_tokens = usage.get("prompt_tokens")
        if completion_tokens is None:
            completion_tokens = usage.get("completion_tokens")

        self.last = {
            "finish_reason": done_reason,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }

    def summary(self) -> str:
        if not self.last:
            return ""
        parts = []
        fr = self.last.get("finish_reason")
        if fr:
            parts.append(f'finish_reason="{fr}"')
        pt = self.last.get("prompt_tokens")
        if pt is not None:
            parts.append(f"prompt_tokens={pt}")
        ct = self.last.get("completion_tokens")
        if ct is not None:
            parts.append(f"completion_tokens={ct}")
        return ", ".join(parts)
