"""SubscribeHandler -- cria subscricoes NGSI-v2 reais no Orion (ADR-0008)."""

from context_broker_agent.agents.base import BaseAgent
from context_broker_agent.config import get_settings
from context_broker_agent.models.messages import AgentMessage, AgentResponse, VerificationResult
from context_broker_agent.services.fiware_client import FiwareClient


class SubscribeHandler(BaseAgent):
    name = "subscribe"

    def __init__(self, client: FiwareClient | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._client = client or FiwareClient()

    async def process(self, message: AgentMessage) -> AgentResponse:
        settings = get_settings()
        entity_type = message.metadata.get("ngsi_query", {}).get("type", "Sensor")
        condition = message.metadata.get("condition", "temperature>25")
        attrs = message.metadata.get("notify_attrs", ["temperature"])

        payload = {
            "description": f"DKRT subscription - {entity_type} - {condition}",
            "subject": {
                "entities": [{"idPattern": ".*", "type": entity_type}],
                "condition": {"attrs": attrs},
            },
            "notification": {
                "http": {"url": f"{settings.quantumleap_url}/v2/notify"},
                "attrs": attrs,
            },
        }

        try:
            subscription_id = await self._client.create_subscription(payload)
        except Exception as exc:
            return AgentResponse(
                agent_name=self.name,
                success=False,
                message=f"Falha ao criar subscrição: {exc}",
            )

        if not subscription_id:
            return AgentResponse(
                agent_name=self.name,
                success=False,
                message="Orion não retornou o id da subscrição (header Location ausente).",
            )

        return AgentResponse(
            agent_name=self.name,
            success=True,
            message=f"Subscrição {subscription_id} criada — notificando QuantumLeap em {settings.quantumleap_url}",
            data={"subscription_id": subscription_id, "requested_payload": payload},
        )

    async def verify(self, message: AgentMessage, result: AgentResponse) -> VerificationResult:
        """Re-consulta a subscrição no Orion para confirmar que foi registrada
        (ADR-0002): antes disso o handler nunca verificava nada de verdade."""
        subscription_id = result.data.get("subscription_id")
        if not subscription_id:
            return VerificationResult(ok=False, message="Sem subscription_id para verificar.")

        try:
            current = await self._client.get_subscription(subscription_id)
        except Exception as exc:
            return VerificationResult(
                ok=False,
                message=f"Não foi possível reconsultar a subscrição {subscription_id}: {exc}",
            )

        if not current or not current.get("id"):
            return VerificationResult(
                ok=False,
                diff={"subscription_id": {"esperado": subscription_id, "obtido": None}},
                message=f"Subscrição {subscription_id} não encontrada ao reconsultar.",
            )

        return VerificationResult(ok=True, message=f"Subscrição {subscription_id} confirmada.")

    async def handle_error(self, message: AgentMessage, diff: dict) -> AgentResponse:
        return AgentResponse(
            agent_name=self.name,
            success=False,
            message="Subscrição não verificada — não foi possível confirmar o registro no Orion.",
            data={"diff": diff},
        )