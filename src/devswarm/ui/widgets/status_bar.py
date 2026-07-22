
from __future__ import annotations

from textual.widgets import Static


class StatusBar(Static):
    def __init__(self, session_id: str, mode: str = "idle", model: str = "", **kwargs) -> None:
        self._session_id = session_id
        self._mode = mode
        self._model = model
        super().__init__(**kwargs)

    def on_mount(self) -> None:
        self._render()

    def _render(self) -> None:
        color = {"plan": "yellow", "build": "green", "idle": "dim"}.get(self._mode, "white")
        self.update(
            f"[{color}]● {self._mode.upper()} MODE[/{color}]  "
            f"[dim]session: {self._session_id[:8]}[/dim]"
            + (f"  [dim]model: {self._model}[/dim]" if self._model else "")
        )

    def update_mode(self, mode: str) -> None:
        self._mode = mode
        self._render()

    def update_session(self, session_id: str) -> None:
        self._session_id = session_id
        self._render()
