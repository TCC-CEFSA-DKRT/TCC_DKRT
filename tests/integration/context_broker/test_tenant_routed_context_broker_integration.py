from __future__ import annotations

import httpx
import pytest
from cryptography.fernet import Fernet, MultiFernet
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from auditor.domain.errors import TenantBrokerNotConfiguredError
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.context_broker.tenant_routed_context_broker import (
    TenantRoutedContextBroker,
)
from auditor.infrastructure.persistence.tables import create_all, tenant_accounts_table
from auditor.infrastructure.persistence.tenant_account_repository import TenantAccountRepository

pytestmark = pytest.mark.integration

TENANT_A = Tenant(fiware_service="smart_city_a", fiware_service_path="/")
TENANT_B = Tenant(fiware_service="smart_city_b", fiware_service_path="/")


@pytest.fixture(scope="module")
def postgres_container():
    with PostgresContainer("pgvector/pgvector:pg16") as container:
        yield container


@pytest.fixture
async def engine(postgres_container):
    sync_url = postgres_container.get_connection_url()
    async_url = sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    eng = create_async_engine(async_url)
    await create_all(eng)
    async with eng.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE tenant_accounts"))
    yield eng
    await eng.dispose()


@pytest.fixture
def fernet() -> MultiFernet:
    return MultiFernet([Fernet(Fernet.generate_key())])


@pytest.fixture
def accounts(engine, fernet) -> TenantAccountRepository:
    return TenantAccountRepository(engine, fernet)


def _recording_client(calls: list) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.url.host, request.headers.get("authorization")))
        return httpx.Response(200, json=[])

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestRoutingAndDecryption:
    @pytest.mark.asyncio
    async def test_each_tenant_reaches_its_own_broker_with_the_decrypted_key(self, accounts):
        await accounts.create(
            TENANT_A, broker_url="https://orion-a.example.com", broker_api_key="chave-a"
        )
        await accounts.create(
            TENANT_B, broker_url="https://orion-b.example.com", broker_api_key="chave-b"
        )
        calls: list = []
        broker = TenantRoutedContextBroker(accounts, client=_recording_client(calls))

        await broker.fetch_entities(TENANT_A, None)
        await broker.fetch_entities(TENANT_B, None)

        assert calls == [
            ("orion-a.example.com", "Bearer chave-a"),
            ("orion-b.example.com", "Bearer chave-b"),
        ]


class TestUpdateBrokerTakesEffectImmediately:
    @pytest.mark.asyncio
    async def test_next_call_after_update_broker_uses_the_new_url_and_key(self, accounts):
        await accounts.create(
            TENANT_A, broker_url="https://orion-antigo.example.com", broker_api_key="chave-antiga"
        )
        calls: list = []
        broker = TenantRoutedContextBroker(accounts, client=_recording_client(calls))
        await broker.fetch_entities(TENANT_A, None)

        await accounts.update_broker(
            TENANT_A, broker_url="https://orion-novo.example.com", broker_api_key="chave-nova"
        )
        await broker.fetch_entities(TENANT_A, None)

        assert calls == [
            ("orion-antigo.example.com", "Bearer chave-antiga"),
            ("orion-novo.example.com", "Bearer chave-nova"),
        ]


class TestAccountRemoved:
    @pytest.mark.asyncio
    async def test_deleting_the_row_directly_raises_tenant_broker_not_configured(
        self, accounts, engine
    ):
        await accounts.create(TENANT_A, broker_url="https://orion-a.example.com")
        broker = TenantRoutedContextBroker(accounts, client=_recording_client([]))
        await broker.fetch_entities(TENANT_A, None)

        async with engine.begin() as conn:
            await conn.execute(
                tenant_accounts_table.delete().where(
                    tenant_accounts_table.c.fiware_service == TENANT_A.fiware_service,
                    tenant_accounts_table.c.fiware_service_path == TENANT_A.fiware_service_path,
                )
            )

        with pytest.raises(TenantBrokerNotConfiguredError):
            await broker.fetch_entities(TENANT_A, None)


class TestKeyRotation:
    @pytest.mark.asyncio
    async def test_broker_still_works_after_rotate_encryption_with_the_new_key_first(
        self, engine
    ):
        k1 = Fernet.generate_key()
        k2 = Fernet.generate_key()
        writer = TenantAccountRepository(engine, MultiFernet([Fernet(k1)]))
        await writer.create(
            TENANT_A, broker_url="https://orion-a.example.com", broker_api_key="chave-secreta"
        )
        rotated_accounts = TenantAccountRepository(engine, MultiFernet([Fernet(k2), Fernet(k1)]))
        await rotated_accounts.rotate_encryption()

        calls: list = []
        broker = TenantRoutedContextBroker(rotated_accounts, client=_recording_client(calls))

        await broker.fetch_entities(TENANT_A, None)

        assert calls == [("orion-a.example.com", "Bearer chave-secreta")]
