
from __future__ import annotations

from textual.widgets import Input as TextualInput
from textual.message import Message
from textual import events
from textual.reactive import reactive


class ChatInput(TextualInput):
    class Submitted(Message):
        def __init__(self, text: str) -> None:
            self.text = text
            super().__init__()

    def __init__(self, **kwargs) -> None:
        self._history: list[str] = []
        self._history_index = -1
        super().__init__(**kwargs)

    def action_submit(self) -> None:
        val = self.value.strip()
        if not val:
            return
        self._history.append(val)
        self._history_index = len(self._history)
        self.post_message(self.Submitted(val))
        self.clear()

    def on_key(self, event: events.Key) -> None:
        if event.key == "up" and self._history:
            self._history_index = max(0, self._history_index - 1)
            self.value = self._history[self._history_index]
            self.cursor_position = len(self.value)
        elif event.key == "down":
            if self._history_index < len(self._history) - 1:
                self._history_index += 1
                self.value = self._history[self._history_index]
            else:
                self._history_index = len(self._history)
                self.value = ""
            self.cursor_position = len(self.value)
