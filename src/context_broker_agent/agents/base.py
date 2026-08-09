"""Agente base com timeout configurável."""

import asyncio
import time
from abc import ABC, abstractmethod

from context_broker_multiagent.config import get_settings
from context_broker_multiagent.models.messages import AgentMessage, AgentResponse


class BaseAgent(ABC):
    """Contrato abstrato para agentes DKRT."""

    name: str = "base"

    def __init__(self, timeout_seconds: float | None = None) -> None:
        settings = get_settings()
        self.timeout_seconds = timeout_seconds or settings.agent_timeout_seconds

    @abstractmethod
    async def process(self, message: AgentMessage) -> AgentResponse:
        """Processa a mensagem e retorna resposta."""

    async def execute_with_timeout(self, message: AgentMessage) -> AgentResponse:
        """Executa `process` com limite de tempo."""
        start = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                self.process(message),
                timeout=self.timeout_seconds,
            )
            result.elapsed_ms = (time.perf_counter() - start) * 1000
            return result
        except TimeoutError:
            return AgentResponse(
                agent_name=self.name,
                success=False,
                message=f"Timeout após {self.timeout_seconds}s",
                elapsed_ms=(time.perf_counter() - start) * 1000,
            )
        except Exception as exc:
            return AgentResponse(
                agent_name=self.name,
                success=False,
                message=str(exc),
                elapsed_ms=(time.perf_counter() - start) * 1000,
            )
