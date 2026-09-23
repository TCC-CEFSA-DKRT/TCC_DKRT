"""Fase 4 — CLI (Typer). Ver .cursor/specs/fase4.spec.md, secao 5.1.

O composition root (auditor.infrastructure.config.container) e' substituido
por fakes via monkeypatch nos nomes importados dentro de
auditor.interfaces.cli.main — sem Orion, sem Postgres reais.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from typer.testing import CliRunner

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
