"""Dependencias FastAPI: identificacao de tenant (ver ADR-0019) e acesso aos
objetos do composition root. Em modo self-hosted o tenant vem da conta salva
em `tenant_accounts` (`get_selfhosted_accounts`/`get_single()`), com
fallback para `Settings.fiware_service`/`fiware_service_path` quando nao ha'
conta salva -- a mesma fonte que `/session`, `/config` e
`SelfHostedContextBroker` usam, nunca do header HTTP; em modo SaaS o tenant
vem exclusivamente do JWT emitido por POST /auth/login -- nenhuma auditoria
roda sem tenant identificado, nos dois modos.
"""

from __future__ import annotations

import jwt
from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.config.container import get_selfhosted_accounts, get_settings
from auditor.infrastructure.config.settings import Settings
from auditor.infrastructure.persistence.tenant_account_repository import TenantAccountRepository
from auditor.interfaces.rest.access_tokens import SESSION_COOKIE_NAME, tenant_from_access_token

_bearer = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def session_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> str | None:
    return credentials.credentials if credentials is not None else cookie


async def get_tenant(
    token: str | None = Depends(session_token),
    settings: Settings = Depends(get_settings),
    accounts: TenantAccountRepository | None = Depends(get_selfhosted_accounts),
) -> Tenant:
    if settings.deployment_mode == "saas":
        if token is None:
            raise _unauthorized("Sessao ausente: faca login.")
        try:
            return tenant_from_access_token(token, settings)
        except jwt.InvalidTokenError:
            raise _unauthorized("Token invalido ou expirado.") from None

    account = await accounts.get_single() if accounts is not None else None
    if account is not None:
        return account.tenant
    return Tenant(
        fiware_service=settings.fiware_service, fiware_service_path=settings.fiware_service_path
    )
