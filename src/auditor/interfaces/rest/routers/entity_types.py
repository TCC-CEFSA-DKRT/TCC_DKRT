"""GET /entity-types — descoberta de tipos de entidade ja existentes no
broker do tenant (ContextBrokerPort.list_entity_types), pra tela de
configuracao (self-hosted) e o formulario de auditoria (SaaS) mostrarem uma
lista real em vez do usuario digitar o tipo as cegas. Sempre 200, mesmo com
o broker fora do ar (`broker_reachable=False`, `types=[]`) — descoberta e'
melhor-esforco, nunca deve bloquear quem so quer digitar o tipo manualmente.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from auditor.domain.errors import ContextBrokerUnavailableError
from auditor.domain.ports.context_broker_port import ContextBrokerPort
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.config.container import get_context_broker
from auditor.interfaces.rest.dependencies import get_tenant
from auditor.interfaces.rest.schemas import EntityTypesResponse

router = APIRouter(prefix="/entity-types", tags=["entity-types"])


@router.get("", response_model=EntityTypesResponse)
async def list_entity_types(
    tenant: Tenant = Depends(get_tenant),
    context_broker: ContextBrokerPort = Depends(get_context_broker),
) -> EntityTypesResponse:
    try:
        types = await context_broker.list_entity_types(tenant)
    except ContextBrokerUnavailableError:
        return EntityTypesResponse(types=[], broker_reachable=False)
    return EntityTypesResponse(types=types, broker_reachable=True)
