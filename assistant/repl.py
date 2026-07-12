"""Interactive REPL for the software delivery assistant.

Wraps :func:`assistant.app.build_assistant` in a conversational loop with
streaming output and human-in-the-loop approval for destructive shell commands.
"""

from __future__ import annotations

import argparse
import json
import os
import uuid

from langchain_core.messages import AIMessageChunk, HumanMessage
from langgraph.types import Command

from assistant.config import resolve_assistant_config
from assistant.app import build_assistant
from assistant.diagnostics import ModelDiagHandler


BANNER = """\n╔══════════════════════════════════════════════════════════╗
║  AI Software Delivery Assistant — interactive session     ║
╚══════════════════════════════════════════════════════════╝
Type a request, or a slash command: /help  /mode  /clear  /exit
"""


def _collect_decisions(hitl_request) -> list[dict]:
    requests = getattr(hitl_request, "action_requests", []) or []
    print("\n⏸  Approval required before running:")
    decisions: list[dict] = []
    for ar in requests:
        args = getattr(ar, "args", {})
        name = getattr(ar, "name", "tool")
        print(f"   • {name}({json.dumps(args, default=str)[:200]})")
        choice = input("   Approve? [y/N/e(edit)/r(respond)] ").strip().lower()
        if choice == "e":
            raw = input("   Edited args as JSON: ")
            try:
                edited_args = json.loads(raw)
            except json.JSONDecodeError:
                edited_args = args
            decisions.append({"type": "edit", "edited_action": {"name": name, "args": edited_args}})
        elif choice == "r":
            msg = input("   Response to return: ")
            decisions.append({"type": "respond", "message": msg})
        elif choice == "y":
            decisions.append({"type": "approve"})
        else:
            decisions.append({"type": "reject", "message": "denied by user"})
    return decisions


def _collect_plan_decision(value: dict) -> list[dict]:
    print("\n" + "=" * 60)
    print("📋 PLAN REVIEW — approval required before building")
    print("=" * 60)
    plan = value.get("plan") or ""
    if plan:
        print(plan)
    prompt = value.get("prompt") or "Approve this plan before building? (yes/no): "
    choice = input(f"\n{prompt}").strip().lower()
    approved = choice in ("y", "yes")
    feedback = ""
    if not approved:
        feedback = input("   Feedback for a revised plan (optional): ").strip()
    return [{"choice": "yes" if approved else "no", "feedback": feedback}]


def _drive(agent, inputs, config: dict) -> None:
    diag = ModelDiagHandler()
    run_config = {**config, "callbacks": [diag]}
    stream = agent.stream(inputs, config=run_config, stream_mode="updates")
    printed = False
    for chunk in stream:
        if not isinstance(chunk, dict):
            continue
        if "__interrupt__" in chunk:
            interrupt = chunk["__interrupt__"]
            value = getattr(interrupt[0], "value", interrupt[0])
            if isinstance(value, dict) and value.get("type") == "plan_review":
                decisions = _collect_plan_decision(value)
            else:
                decisions = _collect_decisions(value)
            _drive(agent, Command(resume={"decisions": decisions}), config)
            return
        for node, update in chunk.items():
            if node.startswith("__"):
                continue
            if not isinstance(update, dict):
                continue
            for msg in update.get("messages", []):
                if isinstance(msg, AIMessageChunk) and msg.content:
                    print(msg.content, end="", flush=True)
                    printed = True
                elif isinstance(msg, HumanMessage):
                    pass
    print()
    if not printed:
        detail = diag.summary()
        hint = (
            "Raise the context window: set ASSISTANT_CTX_SIZE (Ollama auto-sets "
            "num_ctx) or the context length in LM Studio, or use a larger model. "
            "See the README."
        )
        if detail:
            print(f"  (no response generated — model {detail}. {hint})", flush=True)
        else:
            print(
                "  (no response generated — the model returned nothing. If this "
                f"recurs, {hint})",
                flush=True,
            )


def run_repl(project_path: str | None = None) -> None:
    cfg = resolve_assistant_config(project_path)
    agent = build_assistant(cfg=cfg)
    thread_id = f"repl-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 400}

    print(BANNER)
    print(f"  Profile : {cfg.profile}  Model: {cfg.model}  Root: {cfg.project_path}")
    print(f"  HITL shell approval: {'on' if cfg.interrupt_shell else 'off'}\n")

    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return

        if not text:
            continue
        if text in ("/exit", "/quit", "/q"):
            print("Goodbye.")
            return
        if text == "/clear":
            thread_id = f"repl-{uuid.uuid4().hex[:8]}"
            config["configurable"]["thread_id"] = thread_id
            print("  Conversation cleared.")
            continue
        if text == "/mode":
            print(f"  profile={cfg.profile} provider={cfg.provider} model={cfg.model} "
                  f"base_url={cfg.base_url} root={cfg.project_path} "
                  f"exec={cfg.execution_mode} sandbox={cfg.sandbox_enabled} "
                  f"plan_mode={cfg.plan_mode}")
            continue
        if text == "/plan":
            new_state = "0" if os.getenv("ASSISTANT_PLAN_MODE") == "1" else "1"
            os.environ["ASSISTANT_PLAN_MODE"] = new_state
            label = "ON" if new_state == "1" else "OFF"
            print(f"  Plan mode: {label} (opencode-style: the assistant will "
                  f"show a plan and pause for approval before building).")
            continue
        if text == "/help":
            print("  /help  show this   /mode  show config   /clear  new conversation")
            print("  /plan  toggle opencode-style plan mode (pause for plan approval)")
            print("  /exit  quit")
            continue

        _drive(agent, {"messages": [("user", text)]}, config)


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive AI Software Delivery Assistant")
    parser.add_argument("--project-path", help="Project root to operate on (default: current directory)")
    parser.add_argument("--profile", choices=["ollama", "local"], help="Runtime profile")
    parser.add_argument("--model", help="Override model (e.g. gemma4:31b-cloud, qwen/qwen3-4b)")
    parser.add_argument("--base-url", help="Override LLM base URL")
    parser.add_argument("--tech-stack", help="Hint the tech stack for new projects")
    args = parser.parse_args()

    if args.profile:
        import os
        os.environ["ASSISTANT_PROFILE"] = args.profile
    if args.model:
        import os
        os.environ["ASSISTANT_MODEL"] = args.model
    if args.base_url:
        import os
        os.environ["ASSISTANT_BASE_URL"] = args.base_url
    if args.tech_stack:
        import os
        os.environ["ASSISTANT_TECH_STACK"] = args.tech_stack

    run_repl(args.project_path)


if __name__ == "__main__":
    main()
