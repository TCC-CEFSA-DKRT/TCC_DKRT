"""IoTProvisionHandler -- provisiona dispositivos no IoT Agent MQTT (ADR-0004).

Diferente de CreateHandler: nao cria uma entidade NGSI diretamente no Orion.
Registra um DISPOSITIVO no IoT Agent, que passa a criar/atualizar a entidade
correspondente no Orion quando o dispositivo publica uma medida via MQTT.
"""

from context_broker_agent.agents.base import BaseAgent
from context_broker_agent.models.messages import AgentMessage, AgentResponse, VerificationResult
from context_broker_agent.services.iot_agent_client import IoTAgentClient


class IoTProvisionHandler(BaseAgent):
    name = "iot_provision"

    def __init__(self, client: IoTAgentClient | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._client = client or IoTAgentClient()

    async def process(self, message: AgentMessage) -> AgentResponse:
        device_data = message.metadata.get("device") or {}
        device_id = device_data.get("device_id")
        entity_type = device_data.get("entity_type", "Device")
        apikey = device_data.get("apikey") or "dkrt-default-apikey"

        if not device_id:
            return AgentResponse(
                agent_name=self.name,
                success=False,
                message="device_id é obrigatório para provisionar um dispositivo.",
            )

        entity_name = device_data.get("entity_name") or f"{entity_type}:{device_id}"
        attributes = device_data.get("attributes", [])

        try:
            await self._client.create_service_group(apikey, entity_type)
            await self._client.provision_device(
                device_id=device_id,
                entity_name=entity_name,
                entity_type=entity_type,
                apikey=apikey,
                attributes=attributes,
            )
        except Exception as exc:
            return AgentResponse(
                agent_name=self.name,
                success=False,
                message=f"Falha ao provisionar dispositivo: {exc}",
            )

        return AgentResponse(
            agent_name=self.name,
            success=True,
            message=f"Dispositivo {device_id} provisionado (entidade {entity_name}).",
            data={"device_id": device_id, "entity_name": entity_name, "entity_type": entity_type},
        )

    async def verify(self, message: AgentMessage, result: AgentResponse) -> VerificationResult:
        """Re-consulta o dispositivo no IoT Agent para confirmar o registro (ADR-0002)."""
        device_id = result.data.get("device_id")
        if not device_id:
            return VerificationResult(ok=False, message="Sem device_id para verificar.")

        try:
            current = await self._client.get_device(device_id)
        except Exception as exc:
            return VerificationResult(
                ok=False,
                message=f"Não foi possível reconsultar o dispositivo {device_id}: {exc}",
            )

        if not current:
            return VerificationResult(
                ok=False,
                diff={"device_id": {"esperado": device_id, "obtido": None}},
                message=f"Dispositivo {device_id} não encontrado ao reconsultar.",
            )

        return VerificationResult(ok=True, message=f"Dispositivo {device_id} confirmado.")

    async def handle_error(self, message: AgentMessage, diff: dict) -> AgentResponse:
        return AgentResponse(
            agent_name=self.name,
            success=False,
            message="Provisionamento não verificado — dispositivo não confirmado no IoT Agent.",
            data={"diff": diff},
        )

        