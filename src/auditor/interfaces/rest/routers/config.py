from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.config.container import get_selfhosted_accounts, get_settings
from auditor.infrastructure.config.settings import Settings
from auditor.infrastructure.persistence.tenant_account_repository import TenantAccountRepository
from auditor.interfaces.rest.schemas import BrokerConfigRequest, BrokerConfigResponse

router = APIRouter(prefix="/config", tags=["config"])


def _no_encryption_key() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="BROKER_API_KEY_ENCRYPTION_KEYS nao configurada; configuracao pela UI indisponivel.",
    )


@router.get("", response_model=BrokerConfigResponse)
async def get_config(
    settings: Settings = Depends(get_settings),
    accounts: TenantAccountRepository | None = Depends(get_selfhosted_accounts),
) -> BrokerConfigResponse:
    if accounts is None:
        return BrokerConfigResponse(
            configured=True,
            broker_url=settings.fiware_broker_url,
            fiware_service=settings.fiware_service,
            fiware_service_path=settings.fiware_service_path,
        )

    account = await accounts.get_single()
    if account is None:
        return BrokerConfigResponse(
            configured=False,
            broker_url=settings.fiware_broker_url,
            fiware_service=settings.fiware_service,
            fiware_service_path=settings.fiware_service_path,
        )
    return BrokerConfigResponse(
        configured=True,
        broker_url=account.broker_url,
        fiware_service=account.tenant.fiware_service,
        fiware_service_path=account.tenant.fiware_service_path,
    )


@router.put("", response_model=BrokerConfigResponse)
async def put_config(
    body: BrokerConfigRequest,
    settings: Settings = Depends(get_settings),
    accounts: TenantAccountRepository | None = Depends(get_selfhosted_accounts),
) -> BrokerConfigResponse:
    if accounts is None:
        raise _no_encryption_key()

    new_tenant = Tenant(
        fiware_service=body.fiware_service, fiware_service_path=body.fiware_service_path
    )
    current = await accounts.get_single()
    if current is None:
        await accounts.create(new_tenant, body.broker_url, broker_api_key=None)
    else:
        await accounts.replace_tenant(
            current.tenant, new_tenant, body.broker_url, broker_api_key=None
        )
    return BrokerConfigResponse(
        configured=True,
        broker_url=body.broker_url,
        fiware_service=body.fiware_service,
        fiware_service_path=body.fiware_service_path,
    )
