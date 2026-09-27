"""Dependencias FastAPI: identificacao de tenant (ver ADR-0019) e acesso aos
objetos do composition root. Em modo self-hosted o tenant vem dos headers
Fiware-Service/Fiware-ServicePath (comportamento original, .cursor/specs/
fase4.spec.md, secao 4.2); em modo SaaS o tenant vem exclusivamente do JWT
emitido por POST /auth/login — nenhuma auditoria roda sem tenant
identificado, nos dois modos.
"""

from __future__ import annotations

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auditor.domain.errors import InvalidTenantError
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.config.container import get_settings
from auditor.infrastructure.config.settings import Settings
from auditor.interfaces.rest.access_tokens import tenant_from_access_token

_bearer = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_tenant(
    fiware_service: str | None = Header(default=None, alias="Fiware-Service"),
    fiware_service_path: str = Header(default="/", alias="Fiware-ServicePath"),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> Tenant:
    if settings.deployment_mode == "saas":
        if credentials is None:
            raise _unauthorized("Token Bearer obrigatorio.")
        try:
            return tenant_from_access_token(credentials.credentials, settings)
        except (jwt.InvalidTokenError, InvalidTenantError):
            raise _unauthorized("Token invalido ou expirado.") from None

    if not fiware_service:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Header 'Fiware-Service' e obrigatorio para identificar o "
                "tenant da requisicao."
            ),
        )
    return Tenant(fiware_service=fiware_service, fiware_service_path=fiware_service_path)
