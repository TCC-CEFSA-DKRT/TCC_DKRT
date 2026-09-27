from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import bcrypt
from cryptography.fernet import MultiFernet
from sqlalchemy import RowMapping, func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.persistence.tables import tenant_accounts_table


def _normalize_email(login_email: str) -> str:
    return login_email.strip().lower()


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 72:
        raise ValueError("password nao pode exceder 72 bytes utf-8 (limite do bcrypt)")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 72:
        return False
    return bcrypt.checkpw(password_bytes, password_hash.encode("ascii"))


@dataclass(frozen=True)
class TenantAccount:
    tenant: Tenant
    broker_url: str
    broker_api_key: str | None
    login_email: str | None
    password_hash: str | None
    created_at: datetime
    updated_at: datetime


class TenantAccountRepository:
    def __init__(
        self, engine: AsyncEngine, fernet: MultiFernet, require_https: bool = False
    ) -> None:
        self._engine = engine
        self._fernet = fernet
        self._require_https = require_https

    def _check_broker_url(self, broker_url: str) -> None:
        if self._require_https and not broker_url.startswith("https://"):
            raise ValueError(
                "DEPLOYMENT_MODE=saas exige broker_url com https:// (ex.: https://orion.exemplo.com)"
            )

    def _encrypt(self, value: str | None) -> str | None:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii") if value is not None else None

    async def create(
        self,
        tenant: Tenant,
        broker_url: str,
        broker_api_key: str | None = None,
        login_email: str | None = None,
        password: str | None = None,
    ) -> None:
        self._check_broker_url(broker_url)
        encrypted_api_key = self._encrypt(broker_api_key)
        stored_password_hash = hash_password(password) if password is not None else None
        normalized_email = _normalize_email(login_email) if login_email is not None else None

        async with self._engine.begin() as conn:
            await conn.execute(
                tenant_accounts_table.insert().values(
                    fiware_service=tenant.fiware_service,
                    fiware_service_path=tenant.fiware_service_path,
                    broker_url=broker_url,
                    broker_api_key_encrypted=encrypted_api_key,
                    login_email=normalized_email,
                    password_hash=stored_password_hash,
                )
            )

    async def get_by_tenant(self, tenant: Tenant) -> TenantAccount | None:
        async with self._engine.connect() as conn:
            row = (
                await conn.execute(
                    select(tenant_accounts_table).where(
                        tenant_accounts_table.c.fiware_service == tenant.fiware_service,
                        tenant_accounts_table.c.fiware_service_path
                        == tenant.fiware_service_path,
                    )
                )
            ).mappings().first()
        return self._to_account(row) if row is not None else None

    async def get_by_login_email(self, login_email: str) -> TenantAccount | None:
        async with self._engine.connect() as conn:
            row = (
                await conn.execute(
                    select(tenant_accounts_table).where(
                        tenant_accounts_table.c.login_email == _normalize_email(login_email)
                    )
                )
            ).mappings().first()
        return self._to_account(row) if row is not None else None

    def _to_account(self, row: RowMapping) -> TenantAccount:
        decrypted_api_key = (
            self._fernet.decrypt(row["broker_api_key_encrypted"].encode("ascii")).decode("utf-8")
            if row["broker_api_key_encrypted"] is not None
            else None
        )
        return TenantAccount(
            tenant=Tenant(
                fiware_service=row["fiware_service"],
                fiware_service_path=row["fiware_service_path"],
            ),
            broker_url=row["broker_url"],
            broker_api_key=decrypted_api_key,
            login_email=row["login_email"],
            password_hash=row["password_hash"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def update_broker(
        self, tenant: Tenant, broker_url: str, broker_api_key: str | None
    ) -> None:
        self._check_broker_url(broker_url)
        encrypted_api_key = self._encrypt(broker_api_key)

        async with self._engine.begin() as conn:
            result = await conn.execute(
                tenant_accounts_table.update()
                .where(
                    tenant_accounts_table.c.fiware_service == tenant.fiware_service,
                    tenant_accounts_table.c.fiware_service_path
                    == tenant.fiware_service_path,
                )
                .values(
                    broker_url=broker_url,
                    broker_api_key_encrypted=encrypted_api_key,
                    updated_at=func.now(),
                )
            )

        if result.rowcount == 0:
            raise LookupError(
                f"tenant_account nao encontrado para {tenant.fiware_service}"
                f"/{tenant.fiware_service_path}"
            )

    async def replace_tenant(
        self,
        old_tenant: Tenant,
        new_tenant: Tenant,
        broker_url: str,
        broker_api_key: str | None,
    ) -> None:
        self._check_broker_url(broker_url)
        encrypted_api_key = self._encrypt(broker_api_key)
        async with self._engine.begin() as conn:
            deleted = (
                await conn.execute(
                    tenant_accounts_table.delete()
                    .where(
                        tenant_accounts_table.c.fiware_service == old_tenant.fiware_service,
                        tenant_accounts_table.c.fiware_service_path
                        == old_tenant.fiware_service_path,
                    )
                    .returning(tenant_accounts_table.c.login_email)
                )
            ).first()
            if deleted is None:
                raise LookupError(
                    f"tenant_account nao encontrado para {old_tenant.fiware_service}"
                    f"/{old_tenant.fiware_service_path}"
                )
            if deleted.login_email is not None:
                raise ValueError(
                    f"tenant_account {old_tenant.fiware_service}"
                    f"/{old_tenant.fiware_service_path} tem login; replace_tenant so' vale "
                    "para contas self-hosted (login e' exclusivo do broker/tenant)"
                )
            await conn.execute(
                tenant_accounts_table.insert().values(
                    fiware_service=new_tenant.fiware_service,
                    fiware_service_path=new_tenant.fiware_service_path,
                    broker_url=broker_url,
                    broker_api_key_encrypted=encrypted_api_key,
                )
            )

    async def rotate_encryption(self) -> int:
        async with self._engine.begin() as conn:
            rows = (
                await conn.execute(
                    select(
                        tenant_accounts_table.c.fiware_service,
                        tenant_accounts_table.c.fiware_service_path,
                        tenant_accounts_table.c.broker_api_key_encrypted,
                    )
                    .where(tenant_accounts_table.c.broker_api_key_encrypted.is_not(None))
                    .order_by(
                        tenant_accounts_table.c.fiware_service,
                        tenant_accounts_table.c.fiware_service_path,
                    )
                    .with_for_update()
                )
            ).all()
            for row in rows:
                await conn.execute(
                    tenant_accounts_table.update()
                    .where(
                        tenant_accounts_table.c.fiware_service == row.fiware_service,
                        tenant_accounts_table.c.fiware_service_path == row.fiware_service_path,
                    )
                    .values(
                        broker_api_key_encrypted=self._fernet.rotate(
                            row.broker_api_key_encrypted.encode("ascii")
                        ).decode("ascii")
                    )
                )
        return len(rows)
