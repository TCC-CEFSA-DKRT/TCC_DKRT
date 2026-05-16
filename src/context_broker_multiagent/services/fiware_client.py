"""Cliente assíncrono NGSI-v2 para Orion Context Broker."""

import asyncio
from typing import Any

import aiohttp

from context_broker_multiagent.config import get_settings
from context_broker_multiagent.models.ngsi import NgsiEntity, NgsiQueryParams


class FiwareError(Exception):
    """Erro de comunicação com o Orion."""


class FiwareClient:
    """Cliente HTTP NGSI-v2 com retry exponencial."""

    def __init__(
        self,
        base_url: str | None = None,
        service: str | None = None,
        service_path: str | None = None,
        api_key: str | None = None,
        max_retries: int = 3,
        cache_ttl: float = 5.0,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.fiware_broker_url).rstrip("/")
        self.service = service or settings.fiware_service
        self.service_path = service_path or settings.fiware_service_path
        self.api_key = api_key or settings.fiware_api_key
        self.max_retries = max_retries
        self.cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, Any]] = {}

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Fiware-Service": self.service,
            "Fiware-ServicePath": self.service_path,
        }
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                timeout = aiohttp.ClientTimeout(total=30)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.request(
                        method,
                        url,
                        headers=self._headers(),
                        params=params,
                        json=json_body,
                    ) as resp:
                        text = await resp.text()
                        if resp.status >= 400:
                            raise FiwareError(f"HTTP {resp.status}: {text[:500]}")
                        if resp.status == 204 or not text:
                            return None
                        return await resp.json(content_type=None)
            except (aiohttp.ClientError, FiwareError) as exc:
                last_error = exc
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2**attempt * 0.5)

        raise FiwareError(str(last_error) if last_error else "Falha desconhecida")

    async def query_entities(self, params: NgsiQueryParams) -> list[dict[str, Any]]:
        """GET /v2/entities."""
        cache_key = f"query:{params.model_dump_json()}"
        cached = self._cache.get(cache_key)
        if cached:
            import time

            if time.time() - cached[0] < self.cache_ttl:
                return cached[1]

        qparams: dict[str, str | int] = {"limit": params.limit}
        if params.type:
            qparams["type"] = params.type
        if params.id:
            qparams["id"] = params.id
        if params.q:
            qparams["q"] = params.q
        if params.attrs:
            qparams["attrs"] = params.attrs

        data = await self._request("GET", "/v2/entities", params=qparams)
        result = data if isinstance(data, list) else []
        import time

        self._cache[cache_key] = (time.time(), result)
        return result

    async def get_entity(self, entity_id: str) -> dict[str, Any]:
        """GET /v2/entities/{entityId}."""
        data = await self._request("GET", f"/v2/entities/{entity_id}")
        return data if isinstance(data, dict) else {}

    async def create_entity(self, entity: NgsiEntity) -> dict[str, Any]:
        """POST /v2/entities."""
        body = {"id": entity.id, "type": entity.type, **entity.attrs}
        await self._request("POST", "/v2/entities", json_body=body)
        return body

    async def update_attributes(self, entity_id: str, attrs: dict[str, Any]) -> None:
        """PATCH /v2/entities/{id}/attrs."""
        await self._request("PATCH", f"/v2/entities/{entity_id}/attrs", json_body=attrs)

    async def delete_entity(self, entity_id: str) -> None:
        """DELETE /v2/entities/{entityId}."""
        await self._request("DELETE", f"/v2/entities/{entity_id}")

    async def check_health(self) -> dict[str, Any]:
        """Verifica conectividade com o Orion."""
        try:
            await self._request("GET", "/version")
            return {"ok": True, "url": self.base_url}
        except FiwareError as exc:
            return {"ok": False, "url": self.base_url, "error": str(exc)}
