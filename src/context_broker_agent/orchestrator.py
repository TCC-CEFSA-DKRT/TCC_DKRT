"""Orquestrador multiagentes com execução paralela assíncrona."""

import asyncio

import structlog

from context_broker_agent.agents import (
    AnalyzeAgent,
    BaseAgent,
    ProvisionAgent,
    QueryAgent,
    RouteAgent,
    SubscribeAgent,
)
from context_broker_agent.models.messages import (
    AgentMessage,
    AgentResponse,
    OrchestrationResult,
    OrchestrationStatus,
)
from context_broker_agent.services.fiware_client import FiwareClient

logger = structlog.get_logger(__name__)


class MultiAgentOrchestrator:
    """Coordena agentes especializados em paralelo."""

    def __init__(
        self,
        agents: list[BaseAgent] | None = None,
        client: FiwareClient | None = None,
    ) -> None:
        fw = client or FiwareClient()
        self._agents: list[BaseAgent] = agents or [
            RouteAgent(),
            QueryAgent(client=fw),
            SubscribeAgent(),
            ProvisionAgent(client=fw),
            AnalyzeAgent(),
        ]

    @property
    def agent_names(self) -> list[str]:
        return [a.name for a in self._agents]

    async def orchestrate(self, query: str, metadata: dict | None = None) -> OrchestrationResult:
        """Executa todos os agentes em paralelo e agrega resultados."""
        meta = dict(metadata or {})
        message = AgentMessage(content=query, metadata=meta)

        logger.info("orchestration_start", correlation_id=message.correlation_id, query=query)

        responses: list[AgentResponse] = await asyncio.gather(
            *[agent.execute_with_timeout(message) for agent in self._agents]
        )

        route_resp = next((r for r in responses if r.agent_name == "route"), None)
        if route_resp and route_resp.success:
            meta["intent"] = route_resp.data.get("intent", meta.get("intent", "query"))

        query_resp = next((r for r in responses if r.agent_name == "query"), None)
        if query_resp and query_resp.success:
            entities = query_resp.data.get("entities", [])
            meta["entities"] = entities
            analyze = next(a for a in self._agents if a.name == "analyze")
            analyze_msg = AgentMessage(
                content=query,
                metadata={**meta, "entities": entities},
                correlation_id=message.correlation_id,
            )
            analyze_resp = await analyze.execute_with_timeout(analyze_msg)
            responses = [r for r in responses if r.agent_name != "analyze"] + [analyze_resp]

        successes = sum(1 for r in responses if r.success)
        if successes == len(responses):
            status = OrchestrationStatus.OK
        elif successes > 0:
            status = OrchestrationStatus.PARTIAL
        else:
            status = OrchestrationStatus.ERROR

        aggregated = {
            "intent": meta.get("intent"),
            "entities_count": len(meta.get("entities", [])),
            "agents": {r.agent_name: r.success for r in responses},
        }

        return OrchestrationResult(
            status=status,
            responses=list(responses),
            aggregated_data=aggregated,
            correlation_id=message.correlation_id,
        )
