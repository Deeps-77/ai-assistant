
from __future__ import annotations

from textual.containers import VerticalScroll
from textual.widgets import Static
from textual.app import ComposeResult

from devswarm.ui.widgets.message import (
    UserMessage,
    AgentMessage,
    PlanTable,
    ApprovalCard,
    TokenBar,
    InfoLine,
)
from devswarm.ui.theme import AGENT_COLORS


def _detect_agent(content: str) -> str:
    for name in AGENT_COLORS:
        tag = f"[{name.upper()}]"
        if tag.lower() in content.lower():
            return name
    return "Agent"


class ChatView(VerticalScroll):
    def compose(self) -> ComposeResult:
        yield Static("", id="chat-spacer")

    def add_user_message(self, text: str) -> None:
        self.mount(UserMessage(text))
        self.scroll_end(animate=False)

    def add_agent_message(self, content: str) -> None:
        agent = _detect_agent(content)
        self.mount(AgentMessage(content, agent_name=agent))
        self.scroll_end(animate=False)

    def add_plan(self, plan: list[dict]) -> None:
        self.mount(PlanTable(plan))
        self.scroll_end(animate=False)

    def add_approval(self, hitl: dict) -> None:
        self.mount(ApprovalCard(hitl))
        self.scroll_end(animate=False)

    def add_token_bar(self, prompt_tokens: int, completion_tokens: int, num_ctx: int) -> None:
        self.mount(TokenBar(prompt_tokens, completion_tokens, num_ctx))
        self.scroll_end(animate=False)

    def add_info(self, text: str) -> None:
        self.mount(InfoLine(text))
        self.scroll_end(animate=False)

    def add_raw(self, widget: Static) -> None:
        self.mount(widget)
        self.scroll_end(animate=False)
