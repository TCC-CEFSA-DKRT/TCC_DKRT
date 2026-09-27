from __future__ import annotations

import pytest
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.persistence.tables import create_all, tenant_accounts_table
from auditor.infrastructure.persistence.tenant_account_repository import (
    TenantAccountRepository,
    verify_password,
)

pytestmark = pytest.mark.integration

TENANT_A = Tenant(fiware_service="smart_city_a", fiware_service_path="/")
TENANT_B = Tenant(fiware_service="smart_city_b", fiware_service_path="/")
TENANT_C = Tenant(fiware_service="smart_city_c", fiware_service_path="/")


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
def repository(engine, fernet) -> TenantAccountRepository:
    return TenantAccountRepository(engine, fernet)


class TestGetByTenant:
    @pytest.mark.asyncio
    async def test_get_by_tenant_returns_none_when_not_found(self, repository):
        account = await repository.get_by_tenant(TENANT_A)

        assert account is None


class TestGetByLoginEmail:
    @pytest.mark.asyncio
    async def test_returns_the_right_account_among_several_saas_accounts(self, repository):
        await repository.create(
            TENANT_A,
            broker_url="https://orion-a.example.com",
            login_email="a@example.com",
            password="senha-a",
        )
        await repository.create(
            TENANT_B,
            broker_url="https://orion-b.example.com",
            login_email="b@example.com",
            password="senha-b",
        )

        account = await repository.get_by_login_email("a@example.com")

        assert account is not None
        assert account.tenant == TENANT_A
        assert verify_password("senha-a", account.password_hash) is True

    @pytest.mark.asyncio
    async def test_normalizes_the_email_the_same_way_create_does(self, repository):
        await repository.create(
            TENANT_A,
            broker_url="https://orion.example.com",
            login_email="tenant@example.com",
            password="senha-super-secreta",
        )

        account = await repository.get_by_login_email("  Tenant@Example.COM ")

        assert account is not None
        assert account.tenant == TENANT_A

    @pytest.mark.asyncio
    async def test_unknown_email_returns_none(self, repository):
        account = await repository.get_by_login_email("ninguem@example.com")

        assert account is None

    @pytest.mark.asyncio
    async def test_empty_email_returns_none_even_with_a_self_hosted_row_present(self, repository):
        await repository.create(TENANT_A, broker_url="https://orion.example.com")

        account = await repository.get_by_login_email("")

        assert account is None


class TestCreate:
    @pytest.mark.asyncio
    async def test_create_saas_account_round_trips(self, repository):
        api_key = "chave-ção-🔑"
        await repository.create(
            TENANT_A,
            broker_url="https://orion.example.com",
            broker_api_key=api_key,
            login_email="tenant@example.com",
            password="senha-super-secreta",
        )

        account = await repository.get_by_tenant(TENANT_A)

        assert account is not None
        assert account.broker_api_key == api_key
        assert account.login_email == "tenant@example.com"
        assert verify_password("senha-super-secreta", account.password_hash) is True
        assert account.created_at is not None
        assert account.updated_at is not None

    @pytest.mark.asyncio
    async def test_broker_api_key_is_encrypted_at_rest(self, repository, engine, fernet):
        plaintext = "chave-em-texto-puro"
        await repository.create(
            TENANT_A, broker_url="https://orion.example.com", broker_api_key=plaintext
        )

        async with engine.connect() as conn:
            raw = (
                await conn.execute(
                    select(tenant_accounts_table.c.broker_api_key_encrypted).where(
                        tenant_accounts_table.c.fiware_service == TENANT_A.fiware_service,
                        tenant_accounts_table.c.fiware_service_path
                        == TENANT_A.fiware_service_path,
                    )
                )
            ).scalar_one()

        assert raw != plaintext
        assert plaintext not in raw
        assert fernet.decrypt(raw.encode("ascii")).decode("utf-8") == plaintext

    @pytest.mark.asyncio
    async def test_password_is_never_stored_in_plaintext(self, repository, engine):
        password = "senha-super-secreta"
        await repository.create(
            TENANT_A,
            broker_url="https://orion.example.com",
            login_email="tenant@example.com",
            password=password,
        )

        async with engine.connect() as conn:
            raw = (
                await conn.execute(
                    select(tenant_accounts_table.c.password_hash).where(
                        tenant_accounts_table.c.fiware_service == TENANT_A.fiware_service,
                        tenant_accounts_table.c.fiware_service_path
                        == TENANT_A.fiware_service_path,
                    )
                )
            ).scalar_one()

        assert raw != password

    @pytest.mark.asyncio
    async def test_self_hosted_row_without_login_or_api_key(self, repository):
        await repository.create(TENANT_A, broker_url="https://orion.example.com")

        account = await repository.get_by_tenant(TENANT_A)

        assert account is not None
        assert account.broker_api_key is None
        assert account.login_email is None
        assert account.password_hash is None

    @pytest.mark.asyncio
    async def test_duplicate_tenant_is_rejected(self, repository):
        await repository.create(TENANT_A, broker_url="https://orion.example.com")

        with pytest.raises(IntegrityError):
            await repository.create(TENANT_A, broker_url="https://outro.example.com")

    @pytest.mark.asyncio
    async def test_duplicate_login_email_is_rejected(self, repository):
        await repository.create(
            TENANT_A,
            broker_url="https://orion.example.com",
            login_email="dup@example.com",
            password="senha-super-secreta",
        )

        with pytest.raises(IntegrityError):
            await repository.create(
                TENANT_B,
                broker_url="https://orion.example.com",
                login_email="dup@example.com",
                password="outra-senha",
            )

    @pytest.mark.asyncio
    async def test_email_without_password_is_rejected(self, repository):
        with pytest.raises(IntegrityError):
            await repository.create(
                TENANT_A,
                broker_url="https://orion.example.com",
                login_email="a@b.c",
                password=None,
            )

    @pytest.mark.asyncio
    async def test_empty_broker_url_is_rejected(self, repository):
        with pytest.raises(IntegrityError):
            await repository.create(TENANT_A, broker_url="")

    @pytest.mark.asyncio
    async def test_login_email_is_normalized_on_create(self, repository):
        await repository.create(
            TENANT_A,
            broker_url="https://orion.example.com",
            login_email="  Tenant@Example.COM ",
            password="senha-super-secreta",
        )

        account = await repository.get_by_tenant(TENANT_A)

        assert account.login_email == "tenant@example.com"

    @pytest.mark.asyncio
    async def test_duplicate_login_email_differing_only_by_case_is_rejected(self, repository):
        await repository.create(
            TENANT_A,
            broker_url="https://orion.example.com",
            login_email="dup@example.com",
            password="senha-super-secreta",
        )

        with pytest.raises(IntegrityError):
            await repository.create(
                TENANT_B,
                broker_url="https://orion.example.com",
                login_email=" DUP@Example.com",
                password="outra-senha",
            )

    @pytest.mark.asyncio
    async def test_same_service_different_path_are_isolated(self, repository):
        tenant_x_a = Tenant(fiware_service="x", fiware_service_path="/a")
        tenant_x_b = Tenant(fiware_service="x", fiware_service_path="/b")
        await repository.create(
            tenant_x_a, broker_url="https://orion.example.com", broker_api_key="chave-a"
        )
        await repository.create(
            tenant_x_b, broker_url="https://orion.example.com", broker_api_key="chave-b"
        )

        account_a = await repository.get_by_tenant(tenant_x_a)
        account_b = await repository.get_by_tenant(tenant_x_b)

        assert account_a.broker_api_key == "chave-a"
        assert account_b.broker_api_key == "chave-b"


class TestUpdateBroker:
    @pytest.mark.asyncio
    async def test_update_broker_changes_url_and_key_and_bumps_updated_at(self, repository):
        await repository.create(
            TENANT_A, broker_url="https://orion-antigo.example.com", broker_api_key="chave-antiga"
        )
        original = await repository.get_by_tenant(TENANT_A)

        await repository.update_broker(
            TENANT_A, broker_url="https://orion-novo.example.com", broker_api_key="chave-nova"
        )
        updated = await repository.get_by_tenant(TENANT_A)

        assert updated.broker_url == "https://orion-novo.example.com"
        assert updated.broker_api_key == "chave-nova"
        assert updated.created_at == original.created_at
        assert updated.updated_at >= original.created_at

    @pytest.mark.asyncio
    async def test_update_broker_on_unknown_tenant_raises_lookup_error(self, repository):
        with pytest.raises(LookupError):
            await repository.update_broker(
                TENANT_A, broker_url="https://orion.example.com", broker_api_key=None
            )


class TestKeyRotation:
    @pytest.mark.asyncio
    async def test_reading_with_a_different_key_raises_invalid_token(self, engine):
        key_one = MultiFernet([Fernet(Fernet.generate_key())])
        key_two = MultiFernet([Fernet(Fernet.generate_key())])
        writer = TenantAccountRepository(engine, key_one)
        reader = TenantAccountRepository(engine, key_two)
        await writer.create(
            TENANT_A, broker_url="https://orion.example.com", broker_api_key="chave-secreta"
        )

        with pytest.raises(InvalidToken):
            await reader.get_by_tenant(TENANT_A)

    @pytest.mark.asyncio
    async def test_rotated_repository_reads_rows_written_with_the_old_key(self, engine):
        k1 = Fernet.generate_key()
        k2 = Fernet.generate_key()
        writer = TenantAccountRepository(engine, MultiFernet([Fernet(k1)]))
        reader = TenantAccountRepository(engine, MultiFernet([Fernet(k2), Fernet(k1)]))
        await writer.create(
            TENANT_A, broker_url="https://orion.example.com", broker_api_key="chave-secreta"
        )

        account = await reader.get_by_tenant(TENANT_A)

        assert account.broker_api_key == "chave-secreta"

    @pytest.mark.asyncio
    async def test_rotated_repository_encrypts_new_writes_with_the_new_key(self, engine):
        k1 = Fernet.generate_key()
        k2 = Fernet.generate_key()
        rotated = TenantAccountRepository(engine, MultiFernet([Fernet(k2), Fernet(k1)]))
        await rotated.create(
            TENANT_B, broker_url="https://orion.example.com", broker_api_key="chave-secreta"
        )

        async with engine.connect() as conn:
            raw = (
                await conn.execute(
                    select(tenant_accounts_table.c.broker_api_key_encrypted).where(
                        tenant_accounts_table.c.fiware_service == TENANT_B.fiware_service,
                        tenant_accounts_table.c.fiware_service_path
                        == TENANT_B.fiware_service_path,
                    )
                )
            ).scalar_one()

        assert Fernet(k2).decrypt(raw.encode("ascii")) == b"chave-secreta"
        with pytest.raises(InvalidToken):
            Fernet(k1).decrypt(raw.encode("ascii"))

    @pytest.mark.asyncio
    async def test_rotate_encryption_reencrypts_rows_with_the_first_key(self, engine):
        k1 = Fernet.generate_key()
        k2 = Fernet.generate_key()
        writer = TenantAccountRepository(engine, MultiFernet([Fernet(k1)]))
        await writer.create(
            TENANT_A, broker_url="https://orion.example.com", broker_api_key="chave-secreta"
        )
        await writer.create(TENANT_B, broker_url="https://orion.example.com")
        rotated = TenantAccountRepository(engine, MultiFernet([Fernet(k2), Fernet(k1)]))

        count = await rotated.rotate_encryption()

        raw = await _raw_api_key(engine, TENANT_A)
        assert count == 1
        assert Fernet(k2).decrypt(raw.encode("ascii")) == b"chave-secreta"
        with pytest.raises(InvalidToken):
            Fernet(k1).decrypt(raw.encode("ascii"))
        only_new_key = TenantAccountRepository(engine, MultiFernet([Fernet(k2)]))
        assert (await only_new_key.get_by_tenant(TENANT_A)).broker_api_key == "chave-secreta"
        assert (await only_new_key.get_by_tenant(TENANT_B)).broker_api_key is None

    @pytest.mark.asyncio
    async def test_rotate_encryption_is_all_or_nothing_when_a_row_is_undecryptable(self, engine):
        k1 = Fernet.generate_key()
        k2 = Fernet.generate_key()
        k3 = Fernet.generate_key()
        await TenantAccountRepository(engine, MultiFernet([Fernet(k1)])).create(
            TENANT_A, broker_url="https://orion.example.com", broker_api_key="chave-a"
        )
        await TenantAccountRepository(engine, MultiFernet([Fernet(k3)])).create(
            TENANT_B, broker_url="https://orion.example.com", broker_api_key="chave-b"
        )
        rotated = TenantAccountRepository(engine, MultiFernet([Fernet(k2), Fernet(k1)]))

        with pytest.raises(InvalidToken):
            await rotated.rotate_encryption()

        raw_a = await _raw_api_key(engine, TENANT_A)
        assert Fernet(k1).decrypt(raw_a.encode("ascii")) == b"chave-a"


async def _raw_api_key(engine, tenant: Tenant) -> str | None:
    async with engine.connect() as conn:
        return (
            await conn.execute(
                select(tenant_accounts_table.c.broker_api_key_encrypted).where(
                    tenant_accounts_table.c.fiware_service == tenant.fiware_service,
                    tenant_accounts_table.c.fiware_service_path == tenant.fiware_service_path,
                )
            )
        ).scalar_one()


async def _count(engine) -> int:
    async with engine.connect() as conn:
        return (
            await conn.execute(select(func.count()).select_from(tenant_accounts_table))
        ).scalar_one()


class TestReplaceTenant:
    @pytest.mark.asyncio
    async def test_replace_moves_self_hosted_account_to_new_tenant(self, repository, engine):
        await repository.create(
            TENANT_A, broker_url="https://orion-1.example.com", broker_api_key="chave-1"
        )

        await repository.replace_tenant(
            TENANT_A, TENANT_C, "https://orion-2.example.com", "chave-2"
        )

        assert await repository.get_by_tenant(TENANT_A) is None
        account_c = await repository.get_by_tenant(TENANT_C)
        assert account_c.broker_url == "https://orion-2.example.com"
        assert account_c.broker_api_key == "chave-2"
        assert account_c.login_email is None
        assert account_c.password_hash is None
        assert await _count(engine) == 1

    @pytest.mark.asyncio
    async def test_replace_refuses_account_with_login_and_keeps_row_intact(
        self, repository, engine
    ):
        await repository.create(
            TENANT_A,
            broker_url="https://orion-1.example.com",
            broker_api_key="chave-1",
            login_email="a@x.com",
            password="senha",
        )

        with pytest.raises(ValueError):
            await repository.replace_tenant(
                TENANT_A, TENANT_C, "https://orion-2.example.com", "chave-2"
            )

        account_a = await repository.get_by_tenant(TENANT_A)
        assert account_a.broker_url == "https://orion-1.example.com"
        assert account_a.broker_api_key == "chave-1"
        assert account_a.login_email == "a@x.com"
        assert verify_password("senha", account_a.password_hash) is True
        assert await repository.get_by_tenant(TENANT_C) is None
        assert await _count(engine) == 1

    @pytest.mark.asyncio
    async def test_replace_unknown_tenant_raises_lookup_error_and_creates_nothing(
        self, repository, engine
    ):
        with pytest.raises(LookupError):
            await repository.replace_tenant(
                TENANT_A, TENANT_C, "https://orion-2.example.com", "chave-2"
            )

        assert await _count(engine) == 0
        assert await repository.get_by_tenant(TENANT_C) is None

    @pytest.mark.asyncio
    async def test_replace_into_existing_tenant_rolls_back_leaving_both_rows_intact(
        self, repository, engine
    ):
        await repository.create(
            TENANT_A, broker_url="https://orion-a.example.com", broker_api_key="chave-a"
        )
        await repository.create(
            TENANT_B, broker_url="https://orion-b.example.com", broker_api_key="chave-b"
        )

        with pytest.raises(IntegrityError):
            await repository.replace_tenant(
                TENANT_A, TENANT_B, "https://orion-x.example.com", "chave-x"
            )

        account_a = await repository.get_by_tenant(TENANT_A)
        account_b = await repository.get_by_tenant(TENANT_B)
        assert account_a.broker_url == "https://orion-a.example.com"
        assert account_a.broker_api_key == "chave-a"
        assert account_b.broker_url == "https://orion-b.example.com"
        assert account_b.broker_api_key == "chave-b"
        assert await _count(engine) == 2

    @pytest.mark.asyncio
    async def test_replace_with_invalid_broker_url_rolls_back_keeping_old_row(
        self, repository, engine
    ):
        await repository.create(
            TENANT_A, broker_url="https://orion-a.example.com", broker_api_key="chave-a"
        )

        with pytest.raises(IntegrityError):
            await repository.replace_tenant(TENANT_A, TENANT_C, "", None)

        assert await repository.get_by_tenant(TENANT_A) is not None
        assert await repository.get_by_tenant(TENANT_C) is None
        assert await _count(engine) == 1

    @pytest.mark.asyncio
    async def test_replace_with_same_tenant_behaves_as_update(self, repository, engine):
        await repository.create(
            TENANT_A, broker_url="https://orion-1.example.com", broker_api_key="chave-1"
        )

        await repository.replace_tenant(
            TENANT_A, TENANT_A, "https://orion-2.example.com", "chave-2"
        )

        account = await repository.get_by_tenant(TENANT_A)
        assert account.broker_url == "https://orion-2.example.com"
        assert account.broker_api_key == "chave-2"
        assert await _count(engine) == 1
