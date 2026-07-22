
from __future__ import annotations

from textual.widgets import Static
from textual.app import ComposeResult
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.text import Text

from devswarm.ui.theme import AGENT_COLORS, COMPLEXITY_COLOR, STATUS_ICON


class UserMessage(Static):
    def __init__(self, text: str, **kwargs) -> None:
        self.message_text = text
        super().__init__(**kwargs)

    def on_mount(self) -> None:
        self.update(
            Panel(
                f"[bold white]{self.message_text}[/bold white]",
                title="[bold]You[/bold]",
                border_style="green",
                padding=(0, 1),
            )
        )


class AgentMessage(Static):
    def __init__(self, content: str, agent_name: str = "Agent", **kwargs) -> None:
        for name in AGENT_COLORS:
            content = content.replace(f"[{name}]", "").replace(f"[{name.upper()}]", "")
        self.message_content = content.strip()
        self.agent_name = agent_name
        color = AGENT_COLORS.get(agent_name, "white")
        self.border_style = color
        super().__init__(**kwargs)

    def on_mount(self) -> None:
        rich_md = Markdown(self.message_content)
        self.update(
            Panel(
                rich_md,
                title=f"[bold {self.border_style}]🤖 {self.agent_name}[/bold {self.border_style}]",
                border_style=self.border_style,
                padding=(0, 1),
            )
        )


class PlanTable(Static):
    def __init__(self, plan: list[dict], **kwargs) -> None:
        self.plan = plan
        super().__init__(**kwargs)

    def on_mount(self) -> None:
        table = Table(
            title="📋 Implementation Plan",
            box=box.ROUNDED,
            border_style="cyan",
            show_lines=True,
            expand=True,
        )
        table.add_column("#", style="dim", width=4)
        table.add_column("Status", width=4)
        table.add_column("Task", style="bold")
        table.add_column("Complexity", width=10)
        table.add_column("Agent", width=10, style="dim")

        for i, task in enumerate(self.plan, 1):
            status = task.get("status", "todo")
            complexity = task.get("complexity", "medium")
            table.add_row(
                str(i),
                STATUS_ICON.get(status, "?"),
                task.get("title", ""),
                f"[{COMPLEXITY_COLOR.get(complexity, 'white')}]{complexity}[/]",
                task.get("agent", ""),
            )
        self.update(table)


class ApprovalCard(Static):
    def __init__(self, hitl: dict, **kwargs) -> None:
        self.hitl = hitl
        super().__init__(**kwargs)

    def on_mount(self) -> None:
        checkpoint = self.hitl.get("checkpoint", "unknown")
        summary = self.hitl.get("action_summary", "")
        options = self.hitl.get("options", ["approve", "reject"])

        opts_text = "  ·  ".join(
            f"[bold green]{o}[/]" if "approve" in o
            else f"[bold red]{o}[/]" if "reject" in o
            else f"[bold yellow]{o}[/]"
            for o in options
        )

        self.update(
            Panel(
                (
                    f"[bold white]{summary}[/bold white]\n\n"
                    f"[dim]Checkpoint:[/dim] [cyan]{checkpoint}[/cyan]\n\n"
                    f"Options: {opts_text}\n\n"
                    "[dim]Or type any message to redirect / edit the plan.[/dim]"
                ),
                title="[bold yellow]⚠  HUMAN APPROVAL REQUIRED[/bold yellow]",
                border_style="yellow",
                padding=(1, 2),
            )
        )


class TokenBar(Static):
    def __init__(self, prompt_tokens: int, completion_tokens: int, num_ctx: int, **kwargs):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.num_ctx = num_ctx
        super().__init__(**kwargs)

    def on_mount(self) -> None:
        self._render()

    def _fmt(self, n: int) -> str:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.1f}K"
        return str(n)

    def _render(self) -> None:
        total = self.prompt_tokens + self.completion_tokens
        ctx_pct = min(100.0, round(total / self.num_ctx * 100, 1)) if self.num_ctx else 0
        bar_len = 20
        filled = int(bar_len * ctx_pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        text = (
            f"[bold]⬆ {self._fmt(self.prompt_tokens)}[/bold] "
            f"[bold]⬇ {self._fmt(self.completion_tokens)}[/bold]  "
            f"[dim]·  ctx {bar}  {self._fmt(total)} / {self._fmt(self.num_ctx)} ({ctx_pct}%)[/dim]"
        )
        self.update(text)

    def update_tokens(self, prompt_tokens: int, completion_tokens: int, num_ctx: int) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.num_ctx = num_ctx
        self._render()


class InfoLine(Static):
    def __init__(self, text: str, **kwargs) -> None:
        super().__init__(f"[dim]ℹ  {text}[/dim]", **kwargs)
