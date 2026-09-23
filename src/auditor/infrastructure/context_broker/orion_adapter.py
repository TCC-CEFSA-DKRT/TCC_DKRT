"""OrionAdapter — implementa ContextBrokerPort contra um Orion Context
Broker (NGSI-v2) real. Ver .cursor/specs/fase4.spec.md, secao 2.

Pagina automaticamente (NGSI-v2 limita a 1000 itens por pagina) — uma
auditoria ampla pode envolver mais entidades do que cabe numa unica
resposta; sem paginacao, o resultado seria silenciosamente incompleto.
"""

from __future__ import annotations

import httpx

from auditor.domain.errors import ContextBrokerUnavailableError
from auditor.domain.ports.context_broker_port import ContextBrokerPort, RawEntity
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant

_PAGE_SIZE = 1000


class OrionAdapter(ContextBrokerPort):
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient()

    async def fetch_entities(
        self,
        tenant: Tenant,
        entity_type: EntityType | None,
        entity_id: str | None = None,
    ) -> list[RawEntity]:
        # Headers do Tenant sao sempre enviados exatamente como especificado
        # — nunca um default silencioso que vazaria dado de outro tenant.
        headers = {
            "Fiware-Service": tenant.fiware_service,
            "Fiware-ServicePath": tenant.fiware_service_path,
        }
        base_params: dict[str, str] = {}
        if entity_type is not None:
            base_params["type"] = entity_type.value
        if entity_id is not None:
            base_params["id"] = entity_id

        entities: list[RawEntity] = []
        offset = 0
        try:
            while True:
                response = await self._client.get(
                    f"{self._base_url}/v2/entities",
                    params={**base_params, "limit": _PAGE_SIZE, "offset": offset},
                    headers=headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                page = response.json()
                entities.extend(page)
                if len(page) < _PAGE_SIZE:
                    break
                offset += _PAGE_SIZE
        except httpx.HTTPStatusError as exc:
            raise ContextBrokerUnavailableError(
                f"Orion respondeu {exc.response.status_code} para {exc.request.url}."
            ) from exc
        except httpx.HTTPError as exc:
            raise ContextBrokerUnavailableError(f"Orion inacessivel: {exc}") from exc

        return entities
