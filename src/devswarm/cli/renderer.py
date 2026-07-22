"""
DevSwarm CLI – Renderer
Rich-based helpers for rendering plans, diffs, agent messages, and approval cards.
"""

from __future__ import annotations

from typing import Any

from rich.columns import Columns
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich import box

console = Console()


# ── Brand header ─────────────────────────────────────────────────────────────

BANNER = """
[bold cyan] ██████╗ ███████╗██╗   ██╗███████╗██╗    ██╗ █████╗ ██████╗ ███╗   ███╗[/]
[bold cyan]██╔══██╗██╔════╝██║   ██║██╔════╝██║    ██║██╔══██╗██╔══██╗████╗ ████║[/]
[bold cyan]██║  ██║█████╗  ██║   ██║███████╗██║ █╗ ██║███████║██████╔╝██╔████╔██║[/]
[bold cyan]██║  ██║██╔══╝  ╚██╗ ██╔╝╚════██║██║███╗██║██╔══██║██╔══██╗██║╚██╔╝██║[/]
[bold cyan]██████╔╝███████╗ ╚████╔╝ ███████║╚███╔███╔╝██║  ██║██║  ██║██║ ╚═╝ ██║[/]
[bold cyan]╚═════╝ ╚══════╝  ╚═══╝  ╚══════╝ ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝[/]
"""

SUBTITLE = "[dim]AI-Driven Multi-Agent Software Delivery Platform  ·  M0 CLI[/dim]"


def render_banner() -> None:
    console.print(BANNER)
    console.print(SUBTITLE, justify="center")
    console.print()


# ── Mode badge ────────────────────────────────────────────────────────────────

def render_mode_badge(mode: str, session_id: str) -> None:
    color = {
        "plan": "yellow",
        "build": "green",
        "idle": "dim",
    }.get(mode, "white")
    console.print(
        f"[{color}]● {mode.upper()} MODE[/{color}]  "
        f"[dim]session: {session_id[:8]}[/dim]",
        end="  ",
    )


# ── Plan rendering ────────────────────────────────────────────────────────────

_STATUS_ICON = {
    "todo": "⬜",
    "in_progress": "🔄",
    "review": "🔍",
    "done": "✅",
    "blocked": "🚫",
}

_COMPLEXITY_COLOR = {
    "low": "green",
    "medium": "yellow",
    "high": "red",
}


def render_plan(plan: list[dict]) -> None:
    if not plan:
        console.print("[dim]No plan yet.[/dim]")
        return

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

    for i, task in enumerate(plan, 1):
        status = task.get("status", "todo")
        complexity = task.get("complexity", "medium")
        table.add_row(
            str(i),
            _STATUS_ICON.get(status, "?"),
            task.get("title", ""),
            f"[{_COMPLEXITY_COLOR.get(complexity, 'white')}]{complexity}[/]",
            task.get("agent", ""),
        )

    console.print(table)


# ── Approval card ─────────────────────────────────────────────────────────────

def render_approval_card(hitl: dict) -> None:
    checkpoint = hitl.get("checkpoint", "unknown")
    summary = hitl.get("action_summary", "")
    options = hitl.get("options", ["approve", "reject"])

    opts_text = "  ·  ".join(
        f"[bold green]{o}[/]" if "approve" in o
        else f"[bold red]{o}[/]" if "reject" in o
        else f"[bold yellow]{o}[/]"
        for o in options
    )

    panel = Panel(
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
    console.print(panel)


# ── Agent message rendering ───────────────────────────────────────────────────

_AGENT_COLORS = {
    "Orchestrator": "magenta",
    "Planner": "blue",
    "Coder": "cyan",
    "Reviewer": "yellow",
    "Tester": "green",
    "HITL": "red",
}


def render_agent_message(content: str) -> None:
    """Render an AIMessage from any agent, detecting which agent sent it."""
    agent_name = "Agent"
    color = "white"
    for name, clr in _AGENT_COLORS.items():
        tag = f"[{name.upper()}]"
        if tag.lower() in content.lower():
            agent_name = name
            color = clr
            break

    # Strip agent prefix tag for cleaner rendering
    for name in _AGENT_COLORS:
        content = content.replace(f"[{name}]", "").replace(f"[{name.upper()}]", "")

    panel = Panel(
        Markdown(content.strip()),
        title=f"[bold {color}]🤖 {agent_name}[/bold {color}]",
        border_style=color,
        padding=(0, 1),
    )
    console.print(panel)


# ── Diff rendering ────────────────────────────────────────────────────────────

def render_diff(diff_text: str, title: str = "Diff") -> None:
    if not diff_text or diff_text == "(no changes)":
        console.print("[dim](no changes)[/dim]")
        return
    syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title=f"[bold]📄 {title}[/bold]", border_style="dim"))


# ── Audit log rendering ───────────────────────────────────────────────────────

def render_audit_log(audit_log: list[dict]) -> None:
    if not audit_log:
        console.print("[dim]Audit log is empty.[/dim]")
        return

    table = Table(
        title="🔍 Audit Log",
        box=box.SIMPLE_HEAVY,
        border_style="dim",
        expand=True,
    )
    table.add_column("Time (UTC)", style="dim", width=22)
    table.add_column("Agent", width=12)
    table.add_column("Action", width=20)
    table.add_column("Summary")

    for entry in audit_log:
        ts = entry.get("timestamp", "")[:19].replace("T", " ")
        agent = entry.get("agent", "")
        action = entry.get("action", "")
        outputs = entry.get("outputs", {})
        summary = str(outputs)[:80]
        color = _AGENT_COLORS.get(agent.capitalize(), "white")
        table.add_row(ts, f"[{color}]{agent}[/]", action, summary)

    console.print(table)


# ── Generic info / error ──────────────────────────────────────────────────────

def print_info(msg: str) -> None:
    console.print(f"[dim]ℹ  {msg}[/dim]")


def print_success(msg: str) -> None:
    console.print(f"[bold green]✅  {msg}[/bold green]")


def print_error(msg: str) -> None:
    console.print(f"[bold red]❌  {msg}[/bold red]")


def print_warning(msg: str) -> None:
    console.print(f"[bold yellow]⚠  {msg}[/bold yellow]")


def print_rule(title: str = "") -> None:
    console.print(Rule(title, style="dim"))
