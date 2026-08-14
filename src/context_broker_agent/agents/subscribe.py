"""SubscribeHandler — planejamento de subscrições NGSI-v2."""

from context_broker_agent.agents.base import BaseAgent
from context_broker_agent.models.messages import AgentMessage, AgentResponse, VerificationResult


class SubscribeHandler(BaseAgent):
    name = "subscribe"

    async def process(self, message: AgentMessage) -> AgentResponse:
        entity_type = message.metadata.get("ngsi_query", {}).get("type", "Sensor")
        condition = message.metadata.get("condition", "temperature>25")

        plan = {
            "description": {
                "entities": [{"id": ".*", "type": entity_type}],
                "attrs": ["temperature"],
                "condition": {"attrs": condition},
            },
            "notification": {
                "http": {"url": "http://localhost:5050/notify"},
                "attrs": ["temperature"],
            },
        }

        return AgentResponse(
            agent_name=self.name,
            success=True,
            message="Plano de subscrição NGSI-v2 gerado (não enviado ao Orion)",
            data={"subscription_plan": plan},
        )

    async def verify(self, message: AgentMessage, result: AgentResponse) -> VerificationResult:
        """LIMITAÇÃO CONHECIDA: process() ainda não envia a subscrição ao Orion
        (ver ADR-0008), então não há nada real para re-consultar ainda. Sempre
        retorna ok=True — isso precisa ser revisado quando o POST for implementado."""
        return VerificationResult(
            ok=True,
            message="Verificação não aplicável: subscrição ainda não é enviada ao Orion (pendente ADR-0008).",
        )

    async def handle_error(self, message: AgentMessage, diff: dict) -> AgentResponse:
        return AgentResponse(
            agent_name=self.name,
            success=False,
            message="Falha ao verificar subscrição.",
            data={"diff": diff},
        )