"""Cliente STH-Comet (ADR-0010) -- backend legado de dados historicos.

Endpoints confirmados na documentacao oficial (telefonicaid/fiware-sth-comet):
- GET    /STH/v2/entities/{entityId}/attrs/{attrName}?type=&lastN=&dateFrom=&dateTo=
- DELETE /STH/v1/contextEntities/type/{entityType}/id/{entityId}/attributes/{attrName}
- DELETE /STH/v1/contextEntities/type/{entityType}/id/{entityId}
"""

from typing import Any

import aiohttp

from context_broker_agent.config import get_settings
from context_broker_agent.services.historical_data_client import HistoricalDataClient


class SthCometError(Exception):
    """Erro de comunicacao com o STH-Comet."""


class SthCometClient(HistoricalDataClient):
    """Cliente HTTP para a API v2 (leitura) / v1 (remocao) do STH-Comet."""

    def __init__(
        self,
        base_url: str | None = None,
        service: str | None = None,
        service_path: str | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.sth_comet_url).rstrip("/")
        self.service = service or settings.fiware_service
        self.service_path = service_path or settings.fiware_service_path

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Fiware-Service": self.service,
            "Fiware-ServicePath": self.service_path,
        }

    async def query_history(
        self,
        entity_id: str,
        attribute: str,
        *,
        entity_type: str | None = None,
        last_n: int | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """GET /STH/v2/entities/{entityId}/attrs/{attrName}. type e
        tecnicamente opcional na URL mas o STH costuma exigir para
        desambiguar; sempre enviamos quando disponivel."""
        params: dict[str, str | int] = {"lastN": last_n or 100}
        if entity_type:
            params["type"] = entity_type
        if from_date:
            params["dateFrom"] = from_date
        if to_date:
            params["dateTo"] = to_date

        url = f"{self.base_url}/STH/v2/entities/{entity_id}/attrs/{attribute}"
        timeout = aiohttp.ClientTimeout(total=15)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=self._headers(), params=params) as resp:
                    text = await resp.text()
                    if resp.status == 404:
                        return []
                    if resp.status >= 400:
                        raise SthCometError(f"HTTP {resp.status}: {text[:300]}")
                    data = await resp.json(content_type=None)
        except aiohttp.ClientError as exc:
            raise SthCometError(str(exc)) from exc

        # formato STH: {"type": "StructuredValue", "values": [{"recvTime": ..., "attrValue": ...}]}
        raw_values = data.get("values", [])
        return [{"value": v.get("attrValue"), "index": v.get("recvTime")} for v in raw_values]

    async def delete_history(
        self,
        entity_id: str,
        *,
        entity_type: str | None = None,
        attribute: str | None = None,
    ) -> None:
        """DELETE /STH/v1/contextEntities/type/{type}/id/{id}[/attributes/{attr}].

        entity_type e OBRIGATORIO na pratica: sem ele nao da para montar a URL
        (o STH exige o tipo no caminho, diferente do QuantumLeap)."""
        if not entity_type:
            raise SthCometError(
                "entity_type é obrigatório para apagar histórico no STH-Comet "
                "(a URL de remoção exige /type/{entityType}/)."
            )

        path = f"/STH/v1/contextEntities/type/{entity_type}/id/{entity_id}"
        if attribute:
            path += f"/attributes/{attribute}"

        url = f"{self.base_url}{path}"
        timeout = aiohttp.ClientTimeout(total=15)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.delete(url, headers=self._headers()) as resp:
                    text = await resp.text()
                    if resp.status not in (200, 204, 404):
                        raise SthCometError(f"HTTP {resp.status}: {text[:300]}")
        except aiohttp.ClientError as exc:
            raise SthCometError(str(exc)) from exc

    async def check_health(self) -> dict[str, Any]:
        url = f"{self.base_url}/admin/log"
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=self._headers()) as resp:
                    return {"ok": resp.status < 500, "url": self.base_url}
        except aiohttp.ClientError as exc:
            return {"ok": False, "url": self.base_url, "error": str(exc)}

            