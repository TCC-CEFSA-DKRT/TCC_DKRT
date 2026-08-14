"""DeleteHandler — remove entidades do FIWARE Orion."""

from context_broker_agent.agents.base import BaseAgent
from context_broker_agent.models.messages import AgentMessage, AgentResponse, VerificationResult
from context_broker_agent.services.fiware_client import FiwareClient


class DeleteHandler(BaseAgent):
    name = "delete"

    def __init__(self, client: FiwareClient | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._client = client or FiwareClient()

    async def process(self, message: AgentMessage) -> AgentResponse:
        intent = message.metadata.get("chat_intent", {})
        entity_id = intent.get("entity_id") or message.metadata.get("entity_id")

        if not entity_id:
            return AgentResponse(
                agent_name=self.name,
                success=False,
                message="Informe entity_id (ex.: Sensor:001) para excluir",
            )

        try:
            await self._client.delete_entity(entity_id)
            return AgentResponse(
                agent_name=self.name,
                success=True,
                message=f"Entidade {entity_id} removida",
                data={"entity_id": entity_id},
            )
        except Exception as exc:
            return AgentResponse(
                agent_name=self.name,
                success=False,
                message=f"Falha ao excluir: {exc}",
            )

    async def verify(self, message: AgentMessage, result: AgentResponse) -> VerificationResult:
        """Confirma que a entidade realmente sumiu do Orion (re-consulta deve falhar)."""
        entity_id = result.data.get("entity_id")
        try:
            await self._client.get_entity(entity_id)
        except Exception:
            # get_entity falhou (ex.: 404) => a entidade não existe mais, exatamente o esperado
            return VerificationResult(ok=True, message=f"Entidade {entity_id} confirmada removida.")
        # se get_entity NÃO falhou, a entidade ainda está lá — a remoção não colou
        return VerificationResult(
            ok=False,
            diff={"entity_id": {"esperado": "removida", "obtido": "ainda existe"}},
            message=f"Entidade {entity_id} ainda existe no Orion após tentativa de remoção.",
        )

    async def handle_error(self, message: AgentMessage, diff: dict) -> AgentResponse:
        return AgentResponse(
            agent_name=self.name,
            success=False,
            message="Remoção não verificada — a entidade ainda existe no Orion.",
            data={"diff": diff},
        )