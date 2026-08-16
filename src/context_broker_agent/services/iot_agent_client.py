"""Cliente do IoT Agent MQTT (ADR-0004) -- provisionamento de dispositivos.

Endpoints confirmados na documentacao oficial FIWARE (tutorials.NGSI-v2,
fiware-iotagent-json, fiware-iotagent-node-lib):
- POST   /iot/services  -- registra grupo de servico (apikey, entity_type, resource)
- GET    /iot/services
- POST   /iot/devices   -- provisiona dispositivo individual
- GET    /iot/devices/{device_id}
- DELETE /iot/devices/{device_id}

Diferenca importante em relacao a CreateHandler: aqui nao se cria uma
entidade NGSI diretamente -- se registra um DISPOSITIVO no IoT Agent, que
por sua vez cria/atualiza a entidade no Orion quando o dispositivo manda
uma medida via MQTT. E por isso que isso nao e so "mais um create".
"""

from typing import Any

import aiohttp

from context_broker_agent.config import get_settings


class IoTAgentError(Exception):
    """Erro de comunicacao com o IoT Agent."""


class IoTAgentClient:
    def __init__(
        self,
        base_url: str | None = None,
        service: str | None = None,
        service_path: str | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.iot_agent_url).rstrip("/")
        self.service = service or settings.fiware_service
        self.service_path = service_path or settings.fiware_service_path

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Fiware-Service": self.service,
            "Fiware-ServicePath": self.service_path,
        }

    async def _request(
        self, method: str, path: str, json_body: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        url = f"{self.base_url}{path}"
        timeout = aiohttp.ClientTimeout(total=15)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(
                    method, url, headers=self._headers(), json=json_body
                ) as resp:
                    text = await resp.text()
                    if resp.status == 404:
                        return None
                    if resp.status >= 400:
                        raise IoTAgentError(f"HTTP {resp.status}: {text[:400]}")
                    if not text:
                        return {}
                    return await resp.json(content_type=None)
        except aiohttp.ClientError as exc:
            raise IoTAgentError(str(exc)) from exc

    async def create_service_group(
        self, apikey: str, entity_type: str, resource: str = "/iot/json"
    ) -> None:
        """POST /iot/services -- registra o grupo de servico (apikey) antes
        de qualquer dispositivo poder ser provisionado nele."""
        settings = get_settings()
        payload = {
            "services": [
                {
                    "apikey": apikey,
                    "cbroker": settings.fiware_broker_url,
                    "entity_type": entity_type,
                    "resource": resource,
                }
            ]
        }
        await self._request("POST", "/iot/services", payload)

    async def provision_device(
        self,
        device_id: str,
        entity_name: str,
        entity_type: str,
        apikey: str,
        attributes: list[dict[str, str]] | None = None,
        transport: str = "MQTT",
    ) -> None:
        """POST /iot/devices."""
        payload = {
            "devices": [
                {
                    "device_id": device_id,
                    "entity_name": entity_name,
                    "entity_type": entity_type,
                    "apikey": apikey,
                    "protocol": "PDI-IoTA-UltraLight",
                    "transport": transport,
                    "attributes": attributes or [],
                }
            ]
        }
        await self._request("POST", "/iot/devices", payload)

    async def get_device(self, device_id: str) -> dict[str, Any] | None:
        """GET /iot/devices/{device_id} -- usado por verify() para confirmar
        que o provisionamento de fato registrou o dispositivo."""
        return await self._request("GET", f"/iot/devices/{device_id}")

    async def delete_device(self, device_id: str) -> None:
        await self._request("DELETE", f"/iot/devices/{device_id}")

    async def check_health(self) -> dict[str, Any]:
        try:
            await self._request("GET", "/iot/about")
            return {"ok": True, "url": self.base_url}
        except IoTAgentError as exc:
            return {"ok": False, "url": self.base_url, "error": str(exc)}