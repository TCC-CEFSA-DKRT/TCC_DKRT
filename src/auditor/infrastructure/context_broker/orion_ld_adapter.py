"""OrionLdAdapter — implementa ContextBrokerPort contra um Orion Context
Broker em modo NGSI-LD. Ver ADR-0023.

Pede `Accept: application/json` (representacao "key-value"/normalizada sem
@context embutido no corpo) em vez de `application/ld+json` -- isso faz o
corpo de cada entidade LD vir estruturalmente parecido com NGSI-v2
(`{"id":..., "type":..., "atributo": {"type": "Property", "value": ...}}`),
entao o NgsiV2Mapper existente (infrastructure/context_broker/
ngsi_v2_mapper.py) consegue processar as duas sem nenhuma mudanca: ele so'
exige que cada atributo seja um dict com a chave "value".

A unica forma de atributo LD que o v2 nao tem e' Relationship
(`{"type": "Relationship", "object": "urn:..."}` -- usa "object" em vez de
"value"). `_normalize_relationships()` copia "object" para "value" antes de
devolver a entidade, assim o Nivel 1 (StructuralValidator) ve um
atributo com "value" em qualquer um dos dois modos, sem precisar saber qual
protocolo buscou aquela entidade.
"""

from __future__ import annotations

from typing import Any

import httpx

from auditor.domain.errors import ContextBrokerUnavailableError
from auditor.domain.ports.context_broker_port import ContextBrokerPort, RawEntity
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant

_PAGE_SIZE = 1000
_ENVELOPE_FIELDS = {"id", "type"}


def orion_ld_headers(tenant: Tenant, api_key: str | None) -> dict[str, str]:
    # NGSI-LD nao tem equivalente a Fiware-ServicePath -- o modelo de
    # escopo/path do LD e' outro (NGSI-LD spec, secao 4.15) e esta fora do
    # escopo desta integracao; so' o tenant (Fiware-Service -> NGSILD-Tenant)
    # e' repassado.
    headers = {"Accept": "application/json"}
    if tenant.fiware_service:
        headers["NGSILD-Tenant"] = tenant.fiware_service
    if api_key is not None:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _normalize_relationships(entity: RawEntity) -> RawEntity:
    normalized: RawEntity = {}
    for key, value in entity.items():
        if key in _ENVELOPE_FIELDS or key == "@context":
            if key != "@context":
                normalized[key] = value
            continue
        if isinstance(value, dict) and "value" not in value and "object" in value:
            value = {**value, "value": value["object"]}
        normalized[key] = value
    return normalized


class OrionLdAdapter(ContextBrokerPort):
    def __init__(
        self,
        base_url: str,
        client: httpx.AsyncClient | None = None,
        *,
        api_key: str | None = None,
    ) -> None:
        self._base_url_raw = base_url
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient()
        self._api_key = api_key

    def _headers(self, tenant: Tenant) -> dict[str, str]:
        return orion_ld_headers(tenant, self._api_key)

    async def broker_url(self, tenant: Tenant) -> str:
        return self._base_url_raw

    async def fetch_entities(
        self,
        tenant: Tenant,
        entity_type: EntityType | None,
        entity_id: str | None = None,
    ) -> list[RawEntity]:
        headers = self._headers(tenant)
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
                    f"{self._base_url}/ngsi-ld/v1/entities",
                    params={**base_params, "limit": _PAGE_SIZE, "offset": offset},
                    headers=headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                page = response.json()
                entities.extend(_normalize_relationships(entity) for entity in page)
                if len(page) < _PAGE_SIZE:
                    break
                offset += _PAGE_SIZE
        except httpx.HTTPStatusError as exc:
            raise ContextBrokerUnavailableError(
                f"Orion-LD respondeu {exc.response.status_code} para {exc.request.url}."
            ) from exc
        except httpx.HTTPError as exc:
            raise ContextBrokerUnavailableError(f"Orion-LD inacessivel: {exc}") from exc

        return entities

    async def list_entity_types(self, tenant: Tenant) -> list[str]:
        # GET /ngsi-ld/v1/types -- a forma da resposta varia por
        # implementacao: alguns brokers devolvem a lista de nomes direto
        # (["Streetlight", ...]), outros o envelope EntityTypeList da spec
        # (`{"type": "EntityTypeList", "typeList": [...]}`). Trata os dois.
        headers = self._headers(tenant)
        try:
            response = await self._client.get(
                f"{self._base_url}/ngsi-ld/v1/types",
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()
            payload: Any = response.json()
        except httpx.HTTPStatusError as exc:
            raise ContextBrokerUnavailableError(
                f"Orion-LD respondeu {exc.response.status_code} para {exc.request.url}."
            ) from exc
        except httpx.HTTPError as exc:
            raise ContextBrokerUnavailableError(f"Orion-LD inacessivel: {exc}") from exc

        if isinstance(payload, dict):
            payload = payload.get("typeList", [])
        return [entry["type"] if isinstance(entry, dict) else entry for entry in payload]
