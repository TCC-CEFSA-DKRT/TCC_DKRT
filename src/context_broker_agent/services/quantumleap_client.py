"""Cliente QuantumLeap (ADR-0003) — implementacao concreta de HistoricalDataClient."""

from typing import Any

import aiohttp

from context_broker_agent.config import get_settings
from context_broker_agent.services.historical_data_client import HistoricalDataClient


class QuantumLeapError(Exception):
    """Erro de comunicacao com o QuantumLeap."""


class QuantumLeapClient(HistoricalDataClient):
    """Cliente HTTP para a API v2 do QuantumLeap (compatible com NGSI-v2)."""

    def __init__(
        self,
        base_url: str | None = None,
        service: str | None = None,
        service_path: str | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.quantumleap_url).rstrip("/")
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
        last_n: int | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """GET /v2/entities/{entityId}/attrs/{attrName}."""
        params: dict[str, str | int] = {}
        if last_n:
            params["lastN"] = last_n
        if from_date:
            params["fromDate"] = from_date
        if to_date:
            params["toDate"] = to_date

        url = f"{self.base_url}/v2/entities/{entity_id}/attrs/{attribute}"
        timeout = aiohttp.ClientTimeout(total=15)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=self._headers(), params=params) as resp:
                    text = await resp.text()
                    if resp.status == 404:
                        return []  # entidade sem historico ainda registrado
                    if resp.status >= 400:
                        raise QuantumLeapError(f"HTTP {resp.status}: {text[:300]}")
                    data = await resp.json(content_type=None)
        except aiohttp.ClientError as exc:
            raise QuantumLeapError(str(exc)) from exc

        values = data.get("values", [])
        index = data.get("index", [])
        return [{"value": v, "index": i} for v, i in zip(values, index)]

    async def check_health(self) -> dict[str, Any]:
        url = f"{self.base_url}/health"
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    return {"ok": resp.status == 200, "url": self.base_url}
        except aiohttp.ClientError as exc:
            return {"ok": False, "url": self.base_url, "error": str(exc)}