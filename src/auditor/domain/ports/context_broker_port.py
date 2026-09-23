"""ContextBrokerPort — ver .cursor/specs/fase4.spec.md, secao 2, e
docs/plano_refatoracao_v3.md, Parte III, 2.2/3.1.

`RawEntity` e' literalmente o JSON de uma entidade NGSI-v2 normalizada, como
o Orion devolve (envelope `{"attr": {"type":..., "value":..., "metadata":
{...}}}` intacto, `id`/`type` no nivel raiz) — nao e' um tipo de dominio com
comportamento proprio, so um alias para deixar as assinaturas legiveis. Quem
remove o envelope e' o `NgsiV2Mapper` (infrastructure/context_broker), nunca
este port.
"""

from __future__ import annotations

from typing import Any, Protocol

from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant

RawEntity = dict[str, Any]


class ContextBrokerPort(Protocol):
    async def fetch_entities(
        self,
        tenant: Tenant,
        entity_type: EntityType | None,
        entity_id: str | None = None,
    ) -> list[RawEntity]:
        """Busca entidades no broker sob o tenant informado.

        `entity_type=None` => todos os tipos (auditoria ampla). `entity_id`
        informado => filtra para aquela entidade especifica, alem do tipo.
        Lista vazia quando o tenant nao tem entidades daquele tipo — nao e'
        erro. Levanta `ContextBrokerUnavailableError` (ver domain/errors.py)
        quando o broker esta inacessivel — nunca deixa uma excecao de
        transporte (httpx, socket) vazar sem contexto para quem chama.
        """
        ...
