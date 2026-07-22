
from __future__ import annotations

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Static
from textual.worker import get_current_worker

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import Command

from devswarm.config import settings
from devswarm.graph.state import DevSwarmState
from devswarm.agents.base import token_tracker
from devswarm.ui.widgets.chat import ChatView
from devswarm.ui.widgets.input import ChatInput
from devswarm.ui.worker import _init_state


CSS = """
Screen {
    layout: vertical;
}

#app-header {
    height: 1;
}

#chat-view {
    height: 1fr;
    padding: 0 1;
    overflow-y: auto;
}

#status-bar {
    height: 2;
    padding: 0 1;
    background: $surface-darken-1;
}

#chat-input {
    height: 1;
    border: none;
    background: $surface-lighten-1;
}
"""


class DevSwarmApp(App):
    TITLE = "DevSwarm"
    SUB_TITLE = "AI-Driven Multi-Agent Software Delivery"

    CSS = CSS
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("tab", "toggle_mode", "Toggle Mode"),
        Binding("ctrl+l", "clear_chat", "Clear Chat"),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._session_id: str = ""
        self._workspace_path: str = ""
        self._current_state: DevSwarmState | None = None
        self._config: dict = {}
        self._graph = None
        self._prev_msg_count: int = 0
        self._is_interrupted: bool = False
        self._session_token_usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0}
        self._mode: str = "plan"

    def compose(self) -> ComposeResult:
        yield Header(id="app-header", show_clock=False)
        yield ChatView(id="chat-view")
        yield Static(id="status-bar")
        yield ChatInput(id="chat-input", placeholder="Type a message... (Tab to toggle mode)")

    def on_mount(self) -> None:
        from devswarm.graph.builder import compiled_graph as graph

        self._graph = graph
        self._session_id, self._workspace_path, self._current_state = _init_state()
        self._config = {"configurable": {"thread_id": self._session_id}}

        self._update_status_bar()
        chat = self.query_one(ChatView)
        chat.add_info(f"Model: [bold]{settings.ollama_model}[/bold]  Base URL: {settings.ollama_base_url}")
        chat.add_info("Type a task description to start, or [cyan]/help[/cyan] for commands.")
        chat.add_info(f"Session: {self._session_id[:8]}  Workspace: {self._workspace_path}")
        self.set_focus(self.query_one(ChatInput))

    def _update_status_bar(self) -> None:
        color = {"plan": "yellow", "build": "green", "idle": "dim"}.get(self._mode, "white")
        t = self._session_token_usage
        bar = self.query_one("#status-bar")
        bar.update(
            f"[{color}]● {self._mode.upper()} MODE[/{color}]  "
            f"[dim]session: {self._session_id[:8]}[/dim]  "
            f"⬆ {self._fmt_tokens(t.get('prompt_tokens',0))}  "
            f"⬇ {self._fmt_tokens(t.get('completion_tokens',0))}  "
            f"ctx {self._ctx_bar(t.get('prompt_tokens',0)+t.get('completion_tokens',0))}"
        )

    def action_toggle_mode(self) -> None:
        modes = {"plan": "build", "build": "plan", "idle": "plan"}
        self._mode = modes.get(self._mode, "plan")
        if self._current_state is not None:
            self._current_state["mode"] = self._mode
        self._update_status_bar()
        self.query_one(ChatView).add_info(f"Switched to [bold]{self._mode.upper()}[/bold] mode")

    def action_clear_chat(self) -> None:
        self.query_one(ChatView).remove_children()

    @on(ChatInput.Submitted)
    def on_chat_input_submitted(self, event: ChatInput.Submitted) -> None:
        text = event.text
        chat = self.query_one(ChatView)

        if text.startswith("/"):
            self._handle_slash(text, chat)
            return

        chat.add_user_message(text)

        if self._is_interrupted and self._current_state is not None:
            chat.add_info("Resuming from HITL checkpoint...")
            self._run_graph_resume(text)
        else:
            self._run_graph(text)

    def _handle_slash(self, cmd: str, chat: ChatView) -> None:
        cmd = cmd.strip().lower()

        if cmd in ("/exit", "/quit"):
            self.exit()
        elif cmd == "/help":
            help_text = (
                "[bold]Available commands:[/bold]\n\n"
                "  [cyan]/help[/cyan]  Show this help\n"
                "  [cyan]/plan[/cyan]  Show current plan\n"
                "  [cyan]/audit[/cyan]  Show audit log\n"
                "  [cyan]/usage[/cyan]  Token usage info\n"
                "  [cyan]/workspace[/cyan]  Show workspace path\n"
                "  [cyan]/mode[/cyan]  Show current mode\n"
                "  [cyan]/session[/cyan]  Show session ID\n"
                "  [cyan]/clear[/cyan]  Clear chat\n"
                "  [cyan]/exit[/cyan]  Exit DevSwarm"
            )
            chat.add_raw(Static(help_text))
        elif cmd == "/plan":
            if self._current_state and self._current_state.get("plan"):
                chat.add_plan(self._current_state["plan"])
            else:
                chat.add_info("No plan yet.")
        elif cmd == "/audit":
            log = self._current_state.get("audit_log") if self._current_state else []
            if log:
                from devswarm.ui.theme import AGENT_COLORS
                from rich.table import Table
                from rich import box

                table = Table(box=box.SIMPLE_HEAVY, border_style="dim", expand=True)
                table.add_column("Time (UTC)", style="dim", width=22)
                table.add_column("Agent", width=12)
                table.add_column("Action", width=20)
                table.add_column("Summary")
                for entry in log:
                    ts = entry.get("timestamp", "")[:19].replace("T", " ")
                    agent = entry.get("agent", "")
                    action = entry.get("action", "")
                    outputs = entry.get("outputs", {})
                    summary = str(outputs)[:80]
                    color = AGENT_COLORS.get(agent.capitalize(), "white")
                    table.add_row(ts, f"[{color}]{agent}[/]", action, summary)
                chat.add_raw(Static(table))
            else:
                chat.add_info("Audit log is empty.")
        elif cmd == "/usage":
            t = self._session_token_usage
            pt = t.get("prompt_tokens", 0)
            ct = t.get("completion_tokens", 0)
            total = pt + ct
            ctx = settings.ollama_num_ctx
            pct = min(100.0, round(total / ctx * 100, 1)) if ctx else 0
            chat.add_info(f"⬆ {self._fmt_tokens(pt)} ⬇ {self._fmt_tokens(ct)}  ·  {self._fmt_tokens(total)} / {self._fmt_tokens(ctx)} ({pct}%)")
        elif cmd == "/workspace":
            ws = self._workspace_path
            chat.add_info(f"Workspace: {ws}")
            from devswarm.tools.file_tools import list_files
            files = list_files.invoke({"workspace": ws})
            chat.add_raw(Static(f"[dim]{files}[/dim]"))
        elif cmd == "/mode":
            chat.add_info(f"Mode: [bold]{self._mode.upper()}[/bold]")
        elif cmd == "/session":
            chat.add_info(f"Session ID: {self._session_id}")
        elif cmd == "/clear":
            self.action_clear_chat()
        else:
            chat.add_info(f"Unknown command: {cmd!r}. Type [cyan]/help[/cyan] for commands.")

    def _run_graph(self, user_input: str) -> None:
        self._run_graph_worker(user_input, is_resume=False)

    def _run_graph_resume(self, resume_value: str) -> None:
        self._run_graph_worker(resume_value, is_resume=True)

    def _run_graph_worker(self, input_val: str, is_resume: bool = False) -> None:
        worker_name = f"graph_{id(input_val)}"

        def run_sync() -> None:
            w = get_current_worker()
            try:
                if is_resume:
                    stream = self._graph.stream(
                        Command(resume=input_val),
                        config=self._config,
                        stream_mode="values",
                    )
                else:
                    state_input = {
                        **(self._current_state or {}),
                        "messages": (self._current_state.get("messages") or [])
                        + [HumanMessage(content=input_val)],
                    }
                    stream = self._graph.stream(
                        state_input,
                        config=self._config,
                        stream_mode="values",
                    )

                last_state = None
                for event in stream:
                    if w.is_cancelled:
                        return
                    last_state = event
                    self.call_from_thread(self._process_event, event)

                if last_state is not None:
                    self.call_from_thread(self._after_stream, last_state)

            except Exception as e:
                self.call_from_thread(lambda: self.query_one(ChatView).add_info(f"Error: {e}"))

        self.run_worker(run_sync, name=worker_name, group="graph", exclusive=True, thread=True)

    def _process_event(self, event: dict) -> None:
        chat = self.query_one(ChatView)
        messages = event.get("messages") or []
        new_messages = messages[self._prev_msg_count:]
        for msg in new_messages:
            if isinstance(msg, AIMessage):
                chat.add_agent_message(str(msg.content))
        self._prev_msg_count = len(messages)

    def _after_stream(self, state: DevSwarmState) -> None:
        self._current_state = state
        self._session_token_usage.update(token_tracker.snapshot())
        chat = self.query_one(ChatView)

        plan = state.get("plan")
        if plan:
            chat.add_plan(plan)

        hitl = state.get("hitl_pending")
        if hitl:
            chat.add_approval(hitl)
            self._is_interrupted = True
        else:
            self._is_interrupted = False

        self._update_status_bar()

    def _fmt_tokens(self, n: int) -> str:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.1f}K"
        return str(n)

    def _ctx_bar(self, total: int) -> str:
        if not settings.ollama_num_ctx:
            return ""
        pct = min(100.0, round(total / settings.ollama_num_ctx * 100, 1))
        filled = int(20 * pct / 100)
        return "█" * filled + "░" * (20 - filled) + f"  {self._fmt_tokens(total)} / {self._fmt_tokens(settings.ollama_num_ctx)} ({pct}%)"


def main() -> None:
    app = DevSwarmApp()
    app.run()
