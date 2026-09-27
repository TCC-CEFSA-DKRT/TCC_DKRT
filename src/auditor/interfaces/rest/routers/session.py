from __future__ import annotations

import jwt
from fastapi import APIRouter, Depends

from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.config.container import get_selfhosted_accounts, get_settings
from auditor.infrastructure.config.settings import Settings
from auditor.infrastructure.persistence.tenant_account_repository import TenantAccountRepository
from auditor.interfaces.rest.access_tokens import tenant_from_access_token
from auditor.interfaces.rest.dependencies import session_token
from auditor.interfaces.rest.schemas import SessionResponse, TenantResponse

router = APIRouter(prefix="/session", tags=["session"])


def _tenant_response(tenant: Tenant) -> TenantResponse:
    return TenantResponse(
        fiware_service=tenant.fiware_service, fiware_service_path=tenant.fiware_service_path
    )


@router.get("", response_model=SessionResponse)
async def get_session(
    token: str | None = Depends(session_token),
    settings: Settings = Depends(get_settings),
    accounts: TenantAccountRepository | None = Depends(get_selfhosted_accounts),
) -> SessionResponse:
    if settings.deployment_mode == "saas":
        tenant = None
        if token is not None:
            try:
                tenant = tenant_from_access_token(token, settings)
            except jwt.InvalidTokenError:
                tenant = None
        return SessionResponse(
            deployment_mode="saas",
            tenant=_tenant_response(tenant) if tenant is not None else None,
        )

    if accounts is None:
        tenant = Tenant(
            fiware_service=settings.fiware_service,
            fiware_service_path=settings.fiware_service_path,
        )
        return SessionResponse(deployment_mode="selfhosted", tenant=_tenant_response(tenant))

    account = await accounts.get_single()
    return SessionResponse(
        deployment_mode="selfhosted",
        tenant=_tenant_response(account.tenant) if account is not None else None,
    )
