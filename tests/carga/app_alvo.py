"""Aplicacao-alvo dos testes de carga: a API REAL (FastAPI, roteamento,
validacao pydantic, serializacao) com as dependencias externas trocadas por
fakes em memoria. Mede, portanto, o custo da camada HTTP/aplicacao do
sistema — NAO mede Orion, Postgres nem o SLM (Ollama), cujo desempenho
depende da infraestrutura e e' tratado como limitacao no relatorio.

Subir:  uvicorn tests.carga.app_alvo:app --port 8099 --workers 1"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from auditor.domain.entities.audit_run import RunStatus, RunSummary
from auditor.domain.ports.audit_repository_port import AuditRunSummaryView, Page
from auditor.domain.ports.command_interpreter_port import AuditCommandInterpretation
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.config.container import (
    get_interpret_audit_command_use_case,
    get_run_audit_use_case,
    get_selfhosted_accounts,
    get_settings,
    get_unit_of_work,
)
from auditor.infrastructure.config.settings import Settings
from auditor.interfaces.rest.app import create_app

_TENANT = Tenant(fiware_service="", fiware_service_path="/")


def _view(i: int) -> AuditRunSummaryView:
    return AuditRunSummaryView(
        id=uuid4(), tenant=_TENANT, entity_type=EntityType("Streetlight"), status=RunStatus.COMPLETED,
        summary=RunSummary(100, 70, 20, 5, 3, 2), started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc), broker_url="http://orion:1026", total_entities_discovered=100,
    )


_VIEWS = [_view(i) for i in range(500)]  # massa fixa: 500 execucoes historicas


class _UseCase:
    async def start(self, tenant, entity_type=None, entity_id=None):
        return uuid4()


class _Interpret:
    async def execute(self, tenant, command_text):
        return AuditCommandInterpretation("Streetlight", None, 0.9, command_text)


class _Repo:
    async def list_runs(self, tenant, f):
        ini = (f.page - 1) * f.page_size
        return Page(items=_VIEWS[ini : ini + f.page_size], page=f.page, page_size=f.page_size, total=len(_VIEWS))

    async def list_run_summaries_over_time(self, tenant, entity_type):
        return _VIEWS[:30]


class _Uow:
    audits = _Repo()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None


def build_app():
    app = create_app(start_background_workers=False)
    app.dependency_overrides[get_run_audit_use_case] = lambda: _UseCase()
    app.dependency_overrides[get_interpret_audit_command_use_case] = lambda: _Interpret()
    app.dependency_overrides[get_unit_of_work] = _Uow
    app.dependency_overrides[get_selfhosted_accounts] = lambda: None
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    return app


app = build_app()
