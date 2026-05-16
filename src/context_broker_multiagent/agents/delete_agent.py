"""DeleteAgent — remove entidades do FIWARE Orion."""

from context_broker_multiagent.agents.base import BaseAgent
from context_broker_multiagent.models.messages import AgentMessage, AgentResponse
from context_broker_multiagent.services.fiware_client import FiwareClient


class DeleteAgent(BaseAgent):
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
