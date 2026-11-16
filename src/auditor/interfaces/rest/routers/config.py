from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from auditor.domain.ports.broker_connection_tester_port import BrokerConnectionTesterPort
from auditor.domain.value_objects.broker_connection import BrokerConnectionCheck
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.config.container import (
    get_broker_connection_tester,
    get_selfhosted_accounts,
    get_settings,
)
from auditor.infrastructure.config.settings import Settings
from auditor.infrastructure.persistence.tenant_account_repository import (
    TenantAccount,
    TenantAccountRepository,
)
from auditor.interfaces.rest.schemas import (
    BrokerConfigRequest,
    BrokerConfigResponse,
    BrokerConnectionTestRequest,
    BrokerConnectionTestResponse,
    BrokerKind,
    BrokerTargetRequest,
)

router = APIRouter(prefix="/config", tags=["config"])

CONNECTION_FAILED_MESSAGE = (
    "O teste de conexão com o broker falhou. Corrija a configuração ou confirme que quer "
    "salvar mesmo assim (save_without_connection)."
)


def _no_encryption_key() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="BROKER_API_KEY_ENCRYPTION_KEYS nao configurada; configuracao pela UI indisponivel.",
    )


def _kind_of(broker_url: str, has_api_key: bool) -> BrokerKind:
    return "cloud" if has_api_key or broker_url.startswith("https://") else "local"


def _connection_response(check: BrokerConnectionCheck) -> BrokerConnectionTestResponse:
    return BrokerConnectionTestResponse(
        status=check.status.value,
        entity_types_count=check.entity_types_count,
        http_status=check.http_status,
    )


def _tenant_of(body: BrokerTargetRequest) -> Tenant:
    return Tenant(fiware_service=body.fiware_service, fiware_service_path=body.fiware_service_path)


def _api_key_for(body: BrokerTargetRequest, current: TenantAccount | None) -> str | None:
    if body.broker_kind == "local":
        return None
    if body.broker_api_key:
        return body.broker_api_key
    return current.broker_api_key if current is not None else None


async def _current_account(accounts: TenantAccountRepository | None) -> TenantAccount | None:
    return await accounts.get_single() if accounts is not None else None


@router.get("", response_model=BrokerConfigResponse)
async def get_config(
    settings: Settings = Depends(get_settings),
    accounts: TenantAccountRepository | None = Depends(get_selfhosted_accounts),
) -> BrokerConfigResponse:
    account = await _current_account(accounts)
    if account is None:
        return BrokerConfigResponse(
            configured=accounts is None,
            broker_url=settings.fiware_broker_url,
            fiware_service=settings.fiware_service,
            fiware_service_path=settings.fiware_service_path,
            broker_kind=_kind_of(settings.fiware_broker_url, has_api_key=False),
            default_local_broker_url=settings.fiware_broker_url,
        )
    has_api_key = account.broker_api_key is not None
    return BrokerConfigResponse(
        configured=True,
        broker_url=account.broker_url,
        fiware_service=account.tenant.fiware_service,
        fiware_service_path=account.tenant.fiware_service_path,
        broker_kind=_kind_of(account.broker_url, has_api_key),
        has_api_key=has_api_key,
        default_local_broker_url=settings.fiware_broker_url,
    )


@router.post("/test", response_model=BrokerConnectionTestResponse)
async def test_connection(
    body: BrokerConnectionTestRequest,
    accounts: TenantAccountRepository | None = Depends(get_selfhosted_accounts),
    tester: BrokerConnectionTesterPort = Depends(get_broker_connection_tester),
) -> BrokerConnectionTestResponse:
    api_key = _api_key_for(body, await _current_account(accounts))
    check = await tester.check(body.broker_url.strip(), _tenant_of(body), api_key)
    return _connection_response(check)


@router.put("", response_model=BrokerConfigResponse)
async def put_config(
    body: BrokerConfigRequest,
    settings: Settings = Depends(get_settings),
    accounts: TenantAccountRepository | None = Depends(get_selfhosted_accounts),
    tester: BrokerConnectionTesterPort = Depends(get_broker_connection_tester),
) -> BrokerConfigResponse:
    if accounts is None:
        raise _no_encryption_key()

    new_tenant = _tenant_of(body)
    current = await accounts.get_single()
    api_key = _api_key_for(body, current)

    connection: BrokerConnectionTestResponse | None = None
    if not body.save_without_connection:
        check = await tester.check(body.broker_url, new_tenant, api_key)
        connection = _connection_response(check)
        if not check.succeeded:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": CONNECTION_FAILED_MESSAGE,
                    "connection": connection.model_dump(),
                },
            )

    if current is None:
        await accounts.create(new_tenant, body.broker_url, broker_api_key=api_key)
    else:
        await accounts.replace_tenant(current.tenant, new_tenant, body.broker_url, broker_api_key=api_key)
    return BrokerConfigResponse(
        configured=True,
        broker_url=body.broker_url,
        fiware_service=body.fiware_service,
        fiware_service_path=body.fiware_service_path,
        broker_kind=body.broker_kind,
        has_api_key=api_key is not None,
        default_local_broker_url=settings.fiware_broker_url,
        connection=connection,
    )
