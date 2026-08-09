"""Indicador visual de progresso no terminal (estilo chat IA)."""

from __future__ import annotations

from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner


class ThinkingStatus:
    """Spinner Rich com mensagens que mudam por etapa do pipeline."""

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()
        self._live: Live | None = None

    def start(self, message: str = "Pensando...") -> None:
        if self._live is not None:
            self.stop()
        self._live = Live(
            self._render(message),
            console=self._console,
            refresh_per_second=12,
            transient=True,
        )
        self._live.start()

    def update(self, message: str) -> None:
        if self._live is None:
            self.start(message)
            return
        self._live.update(self._render(message))

    def stop(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None

    @staticmethod
    def _render(message: str) -> Spinner:
        return Spinner("dots", text=message, style="cyan")
