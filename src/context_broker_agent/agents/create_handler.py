"""CreateHandler — cria entidades no FIWARE Orion."""

from context_broker_agent.agents.base import BaseAgent
from context_broker_agent.models.messages import AgentMessage, AgentResponse, VerificationResult
from context_broker_agent.models.ngsi import NgsiEntity
from context_broker_agent.services.fiware_client import FiwareClient


class CreateHandler(BaseAgent):
    name = "create"

    def __init__(self, client: FiwareClient | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._client = client or FiwareClient()

    async def process(self, message: AgentMessage) -> AgentResponse:
        intent = message.metadata.get("chat_intent", {})
        entity_data = message.metadata.get("entity")

        if entity_data:
            entity = NgsiEntity.model_validate(entity_data)
        else:
            entity_type = intent.get("entity_type") or "Sensor"
            entity_id = intent.get("entity_id") or f"{entity_type}:new"
            attrs: dict = {}
            attr_name = intent.get("attribute")
            if attr_name:
                attrs[attr_name] = {"type": "Float", "value": 0.0}
            else:
                attrs["status"] = {"type": "Text", "value": "active"}
            entity = NgsiEntity(id=entity_id, type=entity_type, attrs=attrs)

        try:
            result = await self._client.create_entity(entity)
            return AgentResponse(
                agent_name=self.name,
                success=True,
                message=f"Entidade {entity.id} criada",
                data={"entity": result, "requested_attrs": entity.attrs},
            )
        except Exception as exc:
            return AgentResponse(
                agent_name=self.name,
                success=False,
                message=f"Falha ao criar: {exc}",
            )

    async def verify(self, message: AgentMessage, result: AgentResponse) -> VerificationResult:
        """Re-consulta a entidade no Orion e compara com o que foi pedido (ADR-0002)."""
        entity_id = result.data.get("entity", {}).get("id")
        requested_attrs = result.data.get("requested_attrs", {})

        if not entity_id:
            return VerificationResult(ok=False, message="Resposta do Orion sem id da entidade.")

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
            return VerificationResult(
                ok=False,
                diff=diff,
                message=f"Divergência ao verificar {entity_id}.",
            )
        return VerificationResult(ok=True, message=f"Entidade {entity_id} verificada com sucesso.")

    async def handle_error(self, message: AgentMessage, diff: dict) -> AgentResponse:
        """Resposta quando a verificação encontra divergência entre o pedido e o Orion."""
        campos = ", ".join(diff.keys()) or "desconhecido"
        return AgentResponse(
            agent_name=self.name,
            success=False,
            message=f"Criação não verificada — divergência em: {campos}",
            data={"diff": diff},
        )