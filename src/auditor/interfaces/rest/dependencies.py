"""Dependencias FastAPI: identificacao de tenant (stub minimo, ver
.cursor/specs/fase4.spec.md, secao 4.2) e acesso aos objetos do composition
root. Auth completa (JWT, secao 3.8 do plano geral) e' escopo de fase
posterior — mas identificar o tenant e' obrigatorio ja' nesta fase: nenhuma
auditoria roda sem tenant identificado, mesmo antes de autenticacao real
existir.
"""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from auditor.domain.value_objects.tenant import Tenant


async def get_tenant(
    fiware_service: str | None = Header(default=None, alias="Fiware-Service"),
    fiware_service_path: str = Header(default="/", alias="Fiware-ServicePath"),
) -> Tenant:
    if not fiware_service:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Header 'Fiware-Service' e obrigatorio para identificar o "
                "tenant da requisicao."
            ),
        )
    return Tenant(fiware_service=fiware_service, fiware_service_path=fiware_service_path)
