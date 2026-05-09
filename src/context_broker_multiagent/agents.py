"""Nucleo simples de orquestracao usado como primeira funcionalidade do TCC."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AgentResult:
    """Resultado padronizado produzido por um agente."""

    agent: str
    status: str
    message: str


class Agent(Protocol):
    """Contrato minimo para agentes especializados."""

    name: str

    def process(self, user_request: str) -> AgentResult:
        """Processa uma solicitacao de usuario."""


@dataclass(frozen=True)
class QueryIntentAgent:
    """Identifica se a solicitacao tem perfil de consulta ao Context Broker."""

    name: str = "QueryIntentAgent"

    def process(self, user_request: str) -> AgentResult:
        normalized_request = user_request.lower()
        keywords = ("consultar", "buscar", "listar", "sensor", "entidade", "context broker")
        matched = any(keyword in normalized_request for keyword in keywords)

        if matched:
            return AgentResult(
                agent=self.name,
                status="ok",
                message="Solicitacao classificada como consulta NGSI-v2.",
            )

        return AgentResult(
            agent=self.name,
            status="attention",
            message="Solicitacao recebida, mas ainda precisa de refinamento de intencao.",
        )


@dataclass(frozen=True)
class BrokerPlanningAgent:
    """Gera um plano inicial de execucao para consulta ao Orion."""

    name: str = "BrokerPlanningAgent"

    def process(self, user_request: str) -> AgentResult:
        if not user_request.strip():
            return AgentResult(
                agent=self.name,
                status="error",
                message="Informe uma solicitacao para que o plano seja gerado.",
            )

        return AgentResult(
            agent=self.name,
            status="ok",
            message=(
                "Plano inicial: validar entrada, montar consulta NGSI-v2, "
                "acionar Orion Context Broker e formatar resposta ao usuario."
            ),
        )


class MultiAgentOrchestrator:
    """Executa os agentes registrados e agrega suas respostas."""

    def __init__(self, agents: list[Agent] | None = None) -> None:
        self._agents = agents or [QueryIntentAgent(), BrokerPlanningAgent()]

    def handle(self, user_request: str) -> dict[str, object]:
        results = [agent.process(user_request) for agent in self._agents]
        overall_status = "ok" if all(result.status == "ok" for result in results) else "attention"

        return {
            "request": user_request,
            "status": overall_status,
            "results": [result.__dict__ for result in results],
        }
