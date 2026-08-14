"""UpdateHandler — atualiza atributos de entidades NGSI-v2."""

from context_broker_agent.agents.base import BaseAgent
from context_broker_agent.models.messages import AgentMessage, AgentResponse, VerificationResult
from context_broker_agent.services.fiware_client import FiwareClient


class UpdateHandler(BaseAgent):
    name = "update"

    def __init__(self, client: FiwareClient | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._client = client or FiwareClient()

    async def process(self, message: AgentMessage) -> AgentResponse:
        intent = message.metadata.get("chat_intent", {})
        entity_id = intent.get("entity_id") or message.metadata.get("entity_id")
        attr = intent.get("attribute") or "temperature"
        value = message.metadata.get("attr_value", 25.0)

        if not entity_id:
            return AgentResponse(
                agent_name=self.name,
                success=False,
                message="Informe entity_id (ex.: Sensor:001) para atualizar",
            )

        attrs = {attr: {"type": "Float", "value": value}}
        try:
            await self._client.update_attributes(entity_id, attrs)
            return AgentResponse(
                agent_name=self.name,
                success=True,
                message=f"Atributo {attr} atualizado em {entity_id}",
                data={"entity_id": entity_id, "attrs": attrs},
            )
        except Exception as exc:
            return AgentResponse(
                agent_name=self.name,
                success=False,
                message=f"Falha ao atualizar: {exc}",
            )

    async def verify(self, message: AgentMessage, result: AgentResponse) -> VerificationResult:
        """Re-consulta a entidade e confere se o novo valor foi realmente salvo."""
        entity_id = result.data.get("entity_id")
        requested_attrs = result.data.get("attrs", {})

        try:
            current = await self._client.get_entity(entity_id)
        except Exception as exc:
            return VerificationResult(
                ok=False,
                message=f"Não foi possível reconsultar {entity_id}: {exc}",
            )

        diff: dict = {}
        for attr_name, requested in requested_attrs.items():
            actual = current.get(attr_name, {})
            requested_value = requested.get("value") if isinstance(requested, dict) else requested
            actual_value = actual.get("value") if isinstance(actual, dict) else actual
            if actual_value != requested_value:
                diff[attr_name] = {"esperado": requested_value, "obtido": actual_value}

        if diff:
            return VerificationResult(ok=False, diff=diff, message=f"Divergência ao verificar {entity_id}.")
        return VerificationResult(ok=True, message=f"Atualização de {entity_id} verificada com sucesso.")

    async def handle_error(self, message: AgentMessage, diff: dict) -> AgentResponse:
        campos = ", ".join(diff.keys()) or "desconhecido"
        return AgentResponse(
            agent_name=self.name,
            success=False,
            message=f"Atualização não verificada — divergência em: {campos}",
            data={"diff": diff},
        )