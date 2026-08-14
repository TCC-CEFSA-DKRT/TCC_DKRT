"""Agente base com timeout configurável."""

import asyncio
import time
from abc import ABC, abstractmethod

from context_broker_agent.config import get_settings
from context_broker_agent.models.messages import AgentMessage, AgentResponse, VerificationResult


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

    async def verify(self, message: AgentMessage, result: AgentResponse) -> VerificationResult:
        """Verificação pós-execução (ADR-0002): re-consulta e compara campo a
        campo. Só se aplica a handlers mutáveis (create/update/delete/subscribe)
        — cada um deve sobrescrever este método com sua própria comparação."""
        raise NotImplementedError(
            f"{self.__class__.__name__} não implementa verify() — "
            "necessário para operações mutáveis (ADR-0002)."
        )

    async def handle_error(self, message: AgentMessage, diff: dict) -> AgentResponse:
        """Resposta quando a verificação falha (dados divergentes). Cada
        handler mutável deve sobrescrever com sua própria estratégia
        (retry automático até max_retries, ou pedir esclarecimento)."""
        raise NotImplementedError(
            f"{self.__class__.__name__} não implementa handle_error() — "
            "necessário para operações mutáveis (ADR-0002)."
        )