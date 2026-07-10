"""
observability/tracing.py

Per-node duration, token counts, estimated cost tracking.
Outputs a summary to stderr and writes a JSONL log to
``logs/trace_<run_id>.jsonl``.
"""

from __future__ import annotations

import os
import json
import time
import atexit
import threading
from pathlib import Path
from typing import Optional, NamedTuple


# Cost per 1K tokens (USD) — approximate for common models.
_MODEL_COST_MAP: dict[str, tuple[float, float]] = {
    "gpt-4o": (0.01, 0.03),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4": (0.03, 0.06),
    "gpt-3.5-turbo": (0.001, 0.002),
    "claude-3-opus": (0.015, 0.075),
    "claude-3-sonnet": (0.003, 0.015),
    "claude-3-haiku": (0.00025, 0.00125),
}
_FALLBACK_COST = (0.001, 0.002)  # per 1K tokens


class TraceRecord(NamedTuple):
    node: str
    start: float
    end: float
    duration_ms: int
    in_chars: int
    out_chars: int
    in_tokens: int
    out_tokens: int
    model: str
    cost_usd: float


class BudgetExceeded(Exception):
    """Raised when the cumulative cost exceeds ``global_budget_usd``."""


class Tracer:
    """Minimal observability tracer for LLM graph runs.

    Usage::

        tracer = Tracer(run_id="run_001")
        tracer.start_run()
        rec = tracer.record_start("planner")
        # ... invoke LLM ...
        tracer.record_end(rec, in_text="...", out_text="...", model="gpt-4o")
        tracer.end_run()
    """

    def __init__(
        self,
        run_id: str = "default",
        log_dir: str = "logs",
        enabled: bool = True,
    ):
        self.run_id = run_id
        self.log_dir = Path(log_dir)
        self.enabled = enabled
        self._records: list[TraceRecord] = []
        self._lock = threading.Lock()
        self._current_start: Optional[str] = None
        self.global_budget_usd: float = float(
            os.environ.get("OBSERVABILITY_BUDGET_USD", "0")
        )
        atexit.register(self._flush_on_exit)

    # ── Lifecycle ──────────────────────────────────────────────

    def start_run(self, run_id: Optional[str] = None) -> None:
        """Record the start of a full workflow run."""
        if run_id:
            self.run_id = run_id
        self._current_start = run_id or self.run_id
        if self.enabled:
            self.log_dir.mkdir(parents=True, exist_ok=True)

    def end_run(self) -> None:
        """Flush records to disk and print summary."""
        self._flush()
        if self._records:
            total_cost = sum(r.cost_usd for r in self._records)
            total_tokens = sum(r.in_tokens + r.out_tokens for r in self._records)
            total_time_ms = sum(r.duration_ms for r in self._records)
            print(
                f"   [tracing] {len(self._records)} calls, "
                f"{total_tokens} tokens, "
                f"${total_cost:.4f} cost, "
                f"{total_time_ms / 1000:.1f}s total",
                file=__import__("sys").stderr,
            )
        self._current_start = None

    # ── Per-node recording ─────────────────────────────────────

    def record_start(self, node: str) -> int:
        """Record the start of a node invocation. Returns an index for
        ``record_end``."""
        with self._lock:
            idx = len(self._records)
            self._records.append(TraceRecord(
                node=node,
                start=time.time(),
                end=0.0,
                duration_ms=0,
                in_chars=0,
                out_chars=0,
                in_tokens=0,
                out_tokens=0,
                model="",
                cost_usd=0.0,
            ))
            return idx

    def record_end(
        self,
        idx: int,
        in_text: str = "",
        out_text: str = "",
        model: str = "",
    ) -> None:
        """Complete a node record, computing tokens and cost."""
        with self._lock:
            if idx < 0 or idx >= len(self._records):
                return
            old = self._records[idx]
            end_time = time.time()
            in_chars = len(in_text)
            out_chars = len(out_text)
            in_tokens = self._estimate_tokens(in_text)
            out_tokens = self._estimate_tokens(out_text)
            cost = self._compute_cost(in_tokens, out_tokens, model)
            duration_ms = int((end_time - old.start) * 1000)

            self._records[idx] = old._replace(
                end=end_time,
                duration_ms=duration_ms,
                in_chars=in_chars,
                out_chars=out_chars,
                in_tokens=in_tokens,
                out_tokens=out_tokens,
                model=model,
                cost_usd=cost,
            )

            if self.global_budget_usd > 0:
                total = sum(r.cost_usd for r in self._records if r.cost_usd > 0)
                if total > self.global_budget_usd:
                    raise BudgetExceeded(
                        f"Budget ${self.global_budget_usd:.4f} exceeded "
                        f"(total ${total:.4f})"
                    )

    # ── Queries ────────────────────────────────────────────────

    def total_calls(self) -> int:
        return len(self._records)

    def total_tokens(self) -> int:
        return sum(r.in_tokens + r.out_tokens for r in self._records)

    def total_cost_usd(self) -> float:
        return sum(r.cost_usd for r in self._records)

    def slowest_nodes(self, n: int = 5) -> list[TraceRecord]:
        return sorted(self._records, key=lambda r: r.duration_ms, reverse=True)[:n]

    # ── Internals ──────────────────────────────────────────────

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token estimate: use tiktoken if available, else chars/4."""
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except ImportError:
            return max(1, len(text) // 4)

    def _compute_cost(self, in_tk: int, out_tk: int, model: str) -> float:
        cost_per_k = _MODEL_COST_MAP.get(model, _FALLBACK_COST)
        return (in_tk / 1000) * cost_per_k[0] + (out_tk / 1000) * cost_per_k[1]

    def _flush(self) -> None:
        if not self.enabled or not self._records:
            return
        path = self.log_dir / f"trace_{self.run_id}.jsonl"
        try:
            with open(path, "a", encoding="utf-8") as f:
                for r in self._records:
                    f.write(json.dumps({
                        "node": r.node,
                        "duration_ms": r.duration_ms,
                        "in_tokens": r.in_tokens,
                        "out_tokens": r.out_tokens,
                        "model": r.model,
                        "cost_usd": round(r.cost_usd, 6),
                    }) + "\n")
        except OSError as e:
            print(f"   [tracing] Failed to write {path}: {e}", file=__import__("sys").stderr)

    def _flush_on_exit(self) -> None:
        if self._records and self._current_start:
            self._flush()


# ── Decorator for per-node tracing ──────────────────────────

_TRACER_STACK: list[Tracer] = []


def trace_node(node_name: str, model: str = ""):
    """Decorator that wraps a graph-node function with tracing.

    Usage::

        @trace_node("planner", model="gpt-4o")
        def planner_node(state):
            ...
    """
    def decorator(func):
        import functools

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            tracer = _TRACER_STACK[-1] if _TRACER_STACK else None
            if tracer is None or not tracer.enabled:
                return func(*args, **kwargs)
            idx = tracer.record_start(node_name)
            result = None
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                in_text = str(args[0]) if args else ""
                out_text = str(result) if result is not None else ""
                tracer.record_end(idx, in_text=in_text, out_text=out_text, model=model)
        return wrapper
    return decorator


def push_tracer(tracer: Tracer) -> None:
    _TRACER_STACK.append(tracer)


def pop_tracer() -> Optional[Tracer]:
    if _TRACER_STACK:
        return _TRACER_STACK.pop()
    return None
