"""Histórico de conversa em memória para o modo chat."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from context_broker_agent.models.intent import ChatIntent


@dataclass
class HistoryTurn:
    """Uma troca usuário ↔ assistente."""

    user: str
    assistant_summary: str
    intent: ChatIntent | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class HistoryManager:
    """Mantém as últimas N interações para contexto do SLM."""

    def __init__(self, max_turns: int = 5) -> None:
        self.max_turns = max_turns
        self._turns: deque[HistoryTurn] = deque(maxlen=max_turns)
        self._pending: dict[str, Any] | None = None

    def add(self, user: str, assistant_summary: str, intent: ChatIntent | None = None) -> None:
        self._turns.append(HistoryTurn(user=user, assistant_summary=assistant_summary, intent=intent))

    def clear(self) -> None:
        self._turns.clear()
        self._pending = None

    def set_pending(self, data: dict[str, Any]) -> None:
        self._pending = data

    def get_pending(self) -> dict[str, Any] | None:
        return self._pending

    def clear_pending(self) -> None:
        self._pending = None

    def list_turns(self) -> list[HistoryTurn]:
        return list(self._turns)

    def context_for_slm(self) -> list[dict[str, str]]:
        """Mensagens no formato Ollama (user/assistant alternados)."""
        messages: list[dict[str, str]] = []
        for turn in self._turns:
            messages.append({"role": "user", "content": turn.user})
            messages.append({"role": "assistant", "content": turn.assistant_summary})
        return messages

    def last_intent(self) -> ChatIntent | None:
        for turn in reversed(self._turns):
            if turn.intent:
                return turn.intent
        return None
