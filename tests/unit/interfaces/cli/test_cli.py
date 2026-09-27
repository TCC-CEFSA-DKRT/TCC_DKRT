"""Fase 4 — CLI (Typer). Ver .cursor/specs/fase4.spec.md, secao 5.1.

O composition root (auditor.infrastructure.config.container) e' substituido
por fakes via monkeypatch nos nomes importados dentro de
auditor.interfaces.cli.main — sem Orion, sem Postgres reais.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from cryptography.fernet import InvalidToken
from sqlalchemy.exc import IntegrityError
from typer.testing import CliRunner

from auditor.application.use_cases.sync_knowledge_base import KnowledgeSyncResult
from auditor.domain.entities.audit_run import AuditRun, RunStatus
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.config.settings import Settings
from auditor.infrastructure.schema_catalog.catalog_index import SyncResult
from auditor.interfaces.cli import main as cli_main

runner = CliRunner()

_TENANT = Tenant(fiware_service="openiot", fiware_service_path="/")


class _FakeUseCase:
    def __init__(self, run: AuditRun):
        self._run = run

    async def execute(self, tenant, entity_type=None, entity_id=None):
        return self._run.id


class _FakeUnitOfWork:
    def __init__(self, run: AuditRun | None):
        self._run = run

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    @property
    def audits(self):
        return self

    async def get_by_id(self, run_id, tenant):
        if self._run is not None and self._run.id == run_id:
            return self._run
        return None


def _completed_run() -> AuditRun:
    run = AuditRun.create(tenant=_TENANT, entity_type=None, broker_url="http://orion:1026")
    run.status = RunStatus.COMPLETED
    run.finished_at = datetime.now(timezone.utc)
    return run


class TestRunCommand:
    def test_successful_run_prints_run_id_and_final_status(self, monkeypatch):
        run = _completed_run()
        monkeypatch.setattr(cli_main, "get_settings", lambda: Settings())
        monkeypatch.setattr(cli_main, "get_run_audit_use_case", lambda: _FakeUseCase(run))
        monkeypatch.setattr(cli_main, "get_unit_of_work", lambda: _FakeUnitOfWork(run))

        result = runner.invoke(cli_main.app, ["run", "--tenant", "openiot", "--entity-type", "Streetlight"])

        assert result.exit_code == 0
        assert str(run.id) in result.stdout
        assert "completed" in result.stdout


class TestStatusCommand:
    def test_unknown_run_id_returns_nonzero_exit_and_clear_message(self, monkeypatch):
        monkeypatch.setattr(cli_main, "get_settings", lambda: Settings())
        monkeypatch.setattr(cli_main, "get_unit_of_work", lambda: _FakeUnitOfWork(None))

        result = runner.invoke(cli_main.app, ["status", "--run-id", str(uuid4()), "--tenant", "openiot"])

        assert result.exit_code != 0
        assert "Traceback" not in result.output
        assert "nao encontrado" in result.output

    def test_existing_run_prints_status(self, monkeypatch):
        run = _completed_run()
        monkeypatch.setattr(cli_main, "get_settings", lambda: Settings())
        monkeypatch.setattr(cli_main, "get_unit_of_work", lambda: _FakeUnitOfWork(run))

        result = runner.invoke(cli_main.app, ["status", "--run-id", str(run.id), "--tenant", "openiot"])

        assert result.exit_code == 0
        assert "completed" in result.stdout


class _FakeSyncCatalogUseCase:
    def __init__(self, result: SyncResult):
        self._result = result

    async def execute(self) -> SyncResult:
        return self._result


class TestCatalogSyncCommand:
    """`audit catalog sync` -- unico gatilho de SyncCatalogUseCase fora dos
    testes unitarios do proprio use case (ver container.get_sync_catalog_use_case
    e o docstring atualizado de application/use_cases/sync_catalog.py)."""

    def test_successful_sync_prints_models_count(self, monkeypatch):
        result = SyncResult(success=True, models_count=42, reason=None)
        monkeypatch.setattr(cli_main, "get_sync_catalog_use_case", lambda: _FakeSyncCatalogUseCase(result))

        invocation = runner.invoke(cli_main.app, ["catalog", "sync"])

        assert invocation.exit_code == 0
        assert "42" in invocation.stdout

    def test_failed_sync_returns_nonzero_exit_with_reason(self, monkeypatch):
        result = SyncResult(success=False, models_count=None, reason="timeout ao contatar o catalogo remoto")
        monkeypatch.setattr(cli_main, "get_sync_catalog_use_case", lambda: _FakeSyncCatalogUseCase(result))

        invocation = runner.invoke(cli_main.app, ["catalog", "sync"])

        assert invocation.exit_code != 0
        assert "Traceback" not in invocation.output
        assert "timeout ao contatar o catalogo remoto" in invocation.output

    def test_unexpected_exception_returns_nonzero_exit_without_raw_traceback(self, monkeypatch):
        class _RaisingUseCase:
            async def execute(self):
                raise RuntimeError("catalogo indisponivel")

        monkeypatch.setattr(cli_main, "get_sync_catalog_use_case", lambda: _RaisingUseCase())

        invocation = runner.invoke(cli_main.app, ["catalog", "sync"])

        assert invocation.exit_code != 0
        assert "Traceback" not in invocation.output
        assert "catalogo indisponivel" in invocation.output


class _FakeSyncKnowledgeBaseUseCase:
    def __init__(self, result: KnowledgeSyncResult):
        self._result = result

    async def execute(self) -> KnowledgeSyncResult:
        return self._result


class TestKnowledgeSyncCommand:
    """`audit knowledge sync` -- unico gatilho de SyncKnowledgeBaseUseCase fora
    dos testes de integracao do proprio use case (mesmo gap ja corrigido para
    o catalogo, ver TestCatalogSyncCommand e container.get_sync_knowledge_base_use_case)."""

    def test_successful_sync_prints_counts(self, monkeypatch):
        result = KnowledgeSyncResult(created=4, updated=0, deleted=0, total=4)
        monkeypatch.setattr(
            cli_main, "get_sync_knowledge_base_use_case", lambda: _FakeSyncKnowledgeBaseUseCase(result)
        )

        invocation = runner.invoke(cli_main.app, ["knowledge", "sync"])

        assert invocation.exit_code == 0
        assert "4 chunks" in invocation.stdout
        assert "4 novos" in invocation.stdout

    def test_unexpected_exception_returns_nonzero_exit_without_raw_traceback(self, monkeypatch):
        class _RaisingUseCase:
            async def execute(self):
                raise RuntimeError("base de dados indisponivel")

        monkeypatch.setattr(cli_main, "get_sync_knowledge_base_use_case", lambda: _RaisingUseCase())

        invocation = runner.invoke(cli_main.app, ["knowledge", "sync"])

        assert invocation.exit_code != 0
        assert "Traceback" not in invocation.output
        assert "base de dados indisponivel" in invocation.output


class _FakeTenantAccountRepository:
    def __init__(self, count: int = 0, error: Exception | None = None, register_error: Exception | None = None):
        self._count = count
        self._error = error
        self._register_error = register_error
        self.create_calls: list[dict] = []

    async def rotate_encryption(self) -> int:
        if self._error is not None:
            raise self._error
        return self._count

    async def create(self, tenant, broker_url, broker_api_key=None, login_email=None, password=None):
        if self._register_error is not None:
            raise self._register_error
        self.create_calls.append(
            {
                "tenant": tenant,
                "broker_url": broker_url,
                "broker_api_key": broker_api_key,
                "login_email": login_email,
                "password": password,
            }
        )


class TestTenantRotateKeysCommand:
    def test_successful_rotation_prints_count(self, monkeypatch):
        monkeypatch.setattr(
            cli_main, "get_tenant_account_repository", lambda: _FakeTenantAccountRepository(3)
        )

        invocation = runner.invoke(cli_main.app, ["tenant", "rotate-keys"])

        assert invocation.exit_code == 0
        assert "3 linhas" in invocation.stdout

    def test_undecryptable_row_returns_nonzero_exit_with_clear_message(self, monkeypatch):
        monkeypatch.setattr(
            cli_main,
            "get_tenant_account_repository",
            lambda: _FakeTenantAccountRepository(error=InvalidToken()),
        )

        invocation = runner.invoke(cli_main.app, ["tenant", "rotate-keys"])

        assert invocation.exit_code != 0
        assert "Traceback" not in invocation.output
        assert "nada foi alterado" in invocation.output

    def test_unexpected_exception_returns_nonzero_exit_without_raw_traceback(self, monkeypatch):
        monkeypatch.setattr(
            cli_main,
            "get_tenant_account_repository",
            lambda: _FakeTenantAccountRepository(
                error=RuntimeError("BROKER_API_KEY_ENCRYPTION_KEYS nao configurada")
            ),
        )

        invocation = runner.invoke(cli_main.app, ["tenant", "rotate-keys"])

        assert invocation.exit_code != 0
        assert "Traceback" not in invocation.output
        assert "BROKER_API_KEY_ENCRYPTION_KEYS nao configurada" in invocation.output


class TestTenantRegisterCommand:
    def test_c1_saas_account_with_email_and_password_never_echoes_the_password(self, monkeypatch):
        fake = _FakeTenantAccountRepository()
        monkeypatch.setattr(cli_main, "get_tenant_account_repository", lambda: fake)

        invocation = runner.invoke(
            cli_main.app,
            [
                "tenant",
                "register",
                "--tenant",
                "openiot",
                "--broker-url",
                "https://orion.example.com",
                "--email",
                "user@example.com",
                "--password",
                "senha-super-secreta",
            ],
        )

        assert invocation.exit_code == 0
        assert len(fake.create_calls) == 1
        assert fake.create_calls[0]["login_email"] == "user@example.com"
        assert fake.create_calls[0]["password"] == "senha-super-secreta"
        assert "senha-super-secreta" not in invocation.output

    def test_c2_email_without_password_generates_and_prints_it_once(self, monkeypatch):
        fake = _FakeTenantAccountRepository()
        monkeypatch.setattr(cli_main, "get_tenant_account_repository", lambda: fake)

        invocation = runner.invoke(
            cli_main.app,
            [
                "tenant",
                "register",
                "--tenant",
                "openiot",
                "--broker-url",
                "https://orion.example.com",
                "--email",
                "user@example.com",
            ],
        )

        assert invocation.exit_code == 0
        generated_password = fake.create_calls[0]["password"]
        assert generated_password is not None
        assert invocation.output.count(generated_password) == 1

    def test_c3_without_email_creates_a_self_hosted_row_and_prints_no_password(self, monkeypatch):
        fake = _FakeTenantAccountRepository()
        monkeypatch.setattr(cli_main, "get_tenant_account_repository", lambda: fake)

        invocation = runner.invoke(
            cli_main.app,
            [
                "tenant",
                "register",
                "--tenant",
                "openiot",
                "--broker-url",
                "https://orion.example.com",
            ],
        )

        assert invocation.exit_code == 0
        assert fake.create_calls[0]["login_email"] is None
        assert fake.create_calls[0]["password"] is None
        assert "Senha inicial" not in invocation.output

    def test_c4_password_without_email_is_rejected_without_calling_create(self, monkeypatch):
        fake = _FakeTenantAccountRepository()
        monkeypatch.setattr(cli_main, "get_tenant_account_repository", lambda: fake)

        invocation = runner.invoke(
            cli_main.app,
            [
                "tenant",
                "register",
                "--tenant",
                "openiot",
                "--broker-url",
                "https://orion.example.com",
                "--password",
                "senha-super-secreta",
            ],
        )

        assert invocation.exit_code != 0
        assert fake.create_calls == []

    def test_c4_empty_password_is_rejected_without_calling_create(self, monkeypatch):
        fake = _FakeTenantAccountRepository()
        monkeypatch.setattr(cli_main, "get_tenant_account_repository", lambda: fake)

        invocation = runner.invoke(
            cli_main.app,
            [
                "tenant",
                "register",
                "--tenant",
                "openiot",
                "--broker-url",
                "https://orion.example.com",
                "--email",
                "user@example.com",
                "--password",
                "",
            ],
        )

        assert invocation.exit_code != 0
        assert fake.create_calls == []

    def test_c5_duplicate_tenant_maps_constraint_name_and_hides_raw_error(self, monkeypatch):
        register_error = IntegrityError(
            "INSERT",
            {"password_hash": "SEGREDO"},
            Exception('duplicate key value violates unique constraint "pk_tenant_accounts"'),
        )
        fake = _FakeTenantAccountRepository(register_error=register_error)
        monkeypatch.setattr(cli_main, "get_tenant_account_repository", lambda: fake)

        invocation = runner.invoke(
            cli_main.app,
            [
                "tenant",
                "register",
                "--tenant",
                "openiot",
                "--broker-url",
                "https://orion.example.com",
            ],
        )

        assert invocation.exit_code != 0
        assert "ja existe conta" in invocation.output
        assert "SEGREDO" not in invocation.output
        assert "Traceback" not in invocation.output

    def test_c6_duplicate_email_maps_constraint_name(self, monkeypatch):
        register_error = IntegrityError(
            "INSERT",
            {"password_hash": "SEGREDO"},
            Exception(
                'duplicate key value violates unique constraint "uq_tenant_accounts_login_email"'
            ),
        )
        fake = _FakeTenantAccountRepository(register_error=register_error)
        monkeypatch.setattr(cli_main, "get_tenant_account_repository", lambda: fake)

        invocation = runner.invoke(
            cli_main.app,
            [
                "tenant",
                "register",
                "--tenant",
                "openiot",
                "--broker-url",
                "https://orion.example.com",
                "--email",
                "user@example.com",
                "--password",
                "senha-super-secreta",
            ],
        )

        assert invocation.exit_code != 0
        assert "email ja esta em uso" in invocation.output
        assert "SEGREDO" not in invocation.output
        assert "Traceback" not in invocation.output

    def test_c7_generic_exception_returns_nonzero_exit_without_traceback(self, monkeypatch):
        fake = _FakeTenantAccountRepository(register_error=RuntimeError("banco indisponivel"))
        monkeypatch.setattr(cli_main, "get_tenant_account_repository", lambda: fake)

        invocation = runner.invoke(
            cli_main.app,
            [
                "tenant",
                "register",
                "--tenant",
                "openiot",
                "--broker-url",
                "https://orion.example.com",
            ],
        )

        assert invocation.exit_code != 0
        assert "Traceback" not in invocation.output
        assert "banco indisponivel" in invocation.output
