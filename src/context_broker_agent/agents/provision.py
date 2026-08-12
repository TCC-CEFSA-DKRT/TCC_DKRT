"""ProvisionAgent — criação/atualização de entidades NGSI-v2."""

from context_broker_agent.agents.base import BaseAgent
from context_broker_agent.models.messages import AgentMessage, AgentResponse
from context_broker_agent.models.ngsi import NgsiEntity
from context_broker_agent.services.fiware_client import FiwareClient


class ProvisionAgent(BaseAgent):
    name = "provision"

    def __init__(self, client: FiwareClient | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._client = client or FiwareClient()

    async def process(self, message: AgentMessage) -> AgentResponse:
        entity_data = message.metadata.get("entity")
        if not entity_data:
            return AgentResponse(
                agent_name=self.name,
                success=False,
                message="Nenhuma entidade em metadata.entity para provisionar",
            )

        try:
            entity = NgsiEntity.model_validate(entity_data)
            result = await self._client.create_entity(entity)
            return AgentResponse(
                agent_name=self.name,
                success=True,
                message=f"Entidade {entity.id} provisionada",
                data={"entity": result},
            )
        except Exception as exc:
            return AgentResponse(
                agent_name=self.name,
                success=False,
                message=f"Falha ao provisionar: {exc}",
            )
