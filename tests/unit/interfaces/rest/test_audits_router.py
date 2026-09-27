"""Fase 4 — GET /audits/{run_id}. Fase 5 — POST /audits (agora via
start()/fila, .cursor/specs/fase5.spec.md secao 5) e
GET /audits/{run_id}/progress|/stream (secao 4).

Testa a API via ASGI in-process (httpx.ASGITransport) — sem servidor de
verdade, sem Orion, sem Postgres, sem fila real: os dependencies do
composition root sao sobrescritos por fakes (app.dependency_overrides),
igual ao padrao recomendado do proprio FastAPI para testes. O lifespan
(que sobe o AuditWorker de verdade — ver app.py) NAO e' disparado pelo
ASGITransport por padrao, entao esses testes nunca dependem dele.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
import pytest

from auditor.domain.entities.audit_run import AuditRun, RunStatus, RunSummary
from auditor.domain.ports.audit_repository_port import AuditRunSummaryView, Page, RunFilters
from auditor.domain.ports.command_interpreter_port import AuditCommandInterpretation
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.config.container import (
    get_interpret_audit_command_use_case,
    get_run_audit_use_case,
    get_unit_of_work,
)
from auditor.interfaces.rest.app import create_app

_TENANT_HEADERS = {"Fiware-Service": "openiot", "Fiware-ServicePath": "/"}


class _FakeUseCase:
    def __init__(self):
        self.started: list[dict] = []

    async def start(self, tenant, entity_type=None, entity_id=None):
        run = AuditRun.create(tenant=tenant, entity_type=entity_type, broker_url="http://orion:1026")
        self.started.append(
            {"tenant": tenant, "entity_type": entity_type, "entity_id": entity_id, "run": run}
        )
        return run.id


class _FakeRepository:
    def __init__(self, runs=None, report_counts=None, run_summaries=None):
        self.runs = runs or {}
        self.report_counts = report_counts or {}
        # Fase 8, secao 0.1/0.2 -- visoes leves (AuditRunSummaryView) para
        # list_runs/list_run_summaries_over_time, guardadas separado de
        # `runs` (que sao agregados AuditRun completos) porque um teste
        # pode querer popular so' uma das duas sem montar o outro.
        self.run_summaries: list[AuditRunSummaryView] = run_summaries or []
        self.last_list_runs_filters: RunFilters | None = None

    async def get_by_id(self, run_id, tenant):
        return self.runs.get((run_id, tenant.fiware_service))

    async def count_reports(self, run_id, tenant):
        return self.report_counts.get((run_id, tenant.fiware_service), 0)

    async def list_runs(self, tenant, filters):
        self.last_list_runs_filters = filters
        matching = [
            view
            for view in self.run_summaries
            if view.tenant.fiware_service == tenant.fiware_service
            and (filters.status is None or view.status == filters.status)
            and (filters.entity_type is None or view.entity_type == filters.entity_type)
        ]
        return Page(items=matching, page=filters.page, page_size=filters.page_size, total=len(matching))

    async def list_run_summaries_over_time(self, tenant, entity_type):
        return [
            view
            for view in self.run_summaries
            if view.tenant.fiware_service == tenant.fiware_service
            and view.entity_type == entity_type
        ]


class _FakeUnitOfWork:
    def __init__(self, repository: _FakeRepository):
        self.audits = repository

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None


class _FakeInterpreterUseCase:
    """Fase 8, secao 0.3 -- fake do InterpretAuditCommandUseCase completo
    (nao so' do CommandInterpreterPort) porque o que o router de fato
    injeta e' o use case (Depends(get_interpret_audit_command_use_case)).
    Guarda os comandos recebidos para o teste confirmar que RunAuditUseCase
    nunca e' tocado por este caminho."""

    def __init__(self, interpretation: AuditCommandInterpretation | None = None):
        self.received_commands: list[str] = []
        self._interpretation = interpretation

    async def execute(self, tenant, command_text: str) -> AuditCommandInterpretation:
        self.received_commands.append(command_text)
        if self._interpretation is not None:
            return self._interpretation
        return AuditCommandInterpretation(
            entity_type=None, entity_id=None, confidence=0.0, raw_command=command_text
        )


@pytest.fixture
def fake_use_case() -> _FakeUseCase:
    return _FakeUseCase()


@pytest.fixture
def fake_interpret_use_case() -> _FakeInterpreterUseCase:
    return _FakeInterpreterUseCase()


@pytest.fixture
def app_and_repo(fake_use_case, fake_interpret_use_case):
    app = create_app()
    repo = _FakeRepository()
    app.dependency_overrides[get_run_audit_use_case] = lambda: fake_use_case
    app.dependency_overrides[get_unit_of_work] = lambda: _FakeUnitOfWork(repo)
    app.dependency_overrides[get_interpret_audit_command_use_case] = lambda: fake_interpret_use_case
    return app, repo


@pytest.fixture
async def client(app_and_repo):
    app, _ = app_and_repo
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestCreateAudit:
    @pytest.mark.asyncio
    async def test_valid_request_returns_202_with_run_id_and_queued_status(self, client, fake_use_case):
        response = await client.post(
            "/audits", json={"entity_type": "Streetlight", "entity_id": None},
            headers=_TENANT_HEADERS,
        )

        assert response.status_code == 202
        body = response.json()
        assert UUID(body["run_id"])
        assert body["status"] == "queued"
        assert len(fake_use_case.started) == 1

    @pytest.mark.asyncio
    async def test_broad_audit_without_entity_type_or_id_is_accepted(self, client):
        response = await client.post("/audits", json={}, headers=_TENANT_HEADERS)

        assert response.status_code == 202

    @pytest.mark.asyncio
    async def test_missing_tenant_header_returns_401(self, client):
        response = await client.post(
            "/audits", json={"entity_type": "Streetlight"}
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_creation_only_starts_the_run_never_processes_it_inline(self, client, fake_use_case):
        # Fase 5: POST /audits so' cria o run e publica o job — nao
        # processa nada dentro da requisicao (O(1), independente do
        # tamanho do lote). _FakeUseCase.start() nao tem nenhum metodo de
        # processamento para chamar aqui de proposito — se o router
        # tentasse chamar algo alem de start(), o teste quebraria com
        # AttributeError.
        response = await client.post(
            "/audits", json={"entity_type": "Streetlight"}, headers=_TENANT_HEADERS
        )

        assert response.status_code == 202
        assert len(fake_use_case.started) == 1
        call = fake_use_case.started[0]
        assert call["tenant"].fiware_service == "openiot"
        assert call["entity_type"].value == "Streetlight"

    @pytest.mark.asyncio
    async def test_start_raising_tenant_broker_not_configured_returns_401(self):
        from auditor.domain.errors import TenantBrokerNotConfiguredError

        class _FailingUseCase:
            async def start(self, tenant, entity_type=None, entity_id=None):
                raise TenantBrokerNotConfiguredError(tenant)

        app = create_app()
        app.dependency_overrides[get_run_audit_use_case] = lambda: _FailingUseCase()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as failing_client:
            response = await failing_client.post(
                "/audits", json={"entity_type": "Streetlight"}, headers=_TENANT_HEADERS
            )

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"


class TestGetAudit:
    @pytest.mark.asyncio
    async def test_existing_run_for_the_tenant_returns_200(self, client, app_and_repo):
        _, repo = app_and_repo
        tenant = Tenant(fiware_service="openiot", fiware_service_path="/")
        run = AuditRun.create(tenant=tenant, entity_type=None, broker_url="http://orion:1026")
        repo.runs[(run.id, tenant.fiware_service)] = run

        response = await client.get(f"/audits/{run.id}", headers=_TENANT_HEADERS)

        assert response.status_code == 200
        assert response.json()["id"] == str(run.id)

    @pytest.mark.asyncio
    async def test_run_belonging_to_another_tenant_returns_404_not_403(self, client, app_and_repo):
        _, repo = app_and_repo
        other_tenant = Tenant(fiware_service="other_city", fiware_service_path="/")
        run = AuditRun.create(tenant=other_tenant, entity_type=None, broker_url="http://orion:1026")
        repo.runs[(run.id, other_tenant.fiware_service)] = run

        response = await client.get(f"/audits/{run.id}", headers=_TENANT_HEADERS)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_unknown_run_id_returns_404(self, client):
        response = await client.get(f"/audits/{uuid4()}", headers=_TENANT_HEADERS)

        assert response.status_code == 404


class TestGetAuditProgress:
    """Fase 5, secao 4.1/4.2."""

    @pytest.mark.asyncio
    async def test_before_total_known_returns_null_total_never_zero(self, client, app_and_repo):
        _, repo = app_and_repo
        tenant = Tenant(fiware_service="openiot", fiware_service_path="/")
        run = AuditRun.create(tenant=tenant, entity_type=None, broker_url="http://orion:1026")
        run.status = RunStatus.RUNNING
        repo.runs[(run.id, tenant.fiware_service)] = run

        response = await client.get(f"/audits/{run.id}/progress", headers=_TENANT_HEADERS)

        assert response.status_code == 200
        body = response.json()
        assert body == {"status": "running", "processed": 0, "total": None}

    @pytest.mark.asyncio
    async def test_processed_reflects_a_real_count_not_the_in_memory_summary(self, client, app_and_repo):
        # Prova que o endpoint usa count_reports() (fonte de verdade no
        # banco), nao run.summary — deixamos run.summary em zero de
        # proposito e configuramos report_counts com outro valor.
        _, repo = app_and_repo
        tenant = Tenant(fiware_service="openiot", fiware_service_path="/")
        run = AuditRun.create(tenant=tenant, entity_type=None, broker_url="http://orion:1026")
        run.status = RunStatus.RUNNING
        run.total_entities_discovered = 500
        repo.runs[(run.id, tenant.fiware_service)] = run
        repo.report_counts[(run.id, tenant.fiware_service)] = 120

        response = await client.get(f"/audits/{run.id}/progress", headers=_TENANT_HEADERS)

        body = response.json()
        assert body == {"status": "running", "processed": 120, "total": 500}
        assert run.summary.total_entities == 0  # confirma que nao veio daqui

    @pytest.mark.asyncio
    async def test_completed_run_has_processed_equal_to_total(self, client, app_and_repo):
        _, repo = app_and_repo
        tenant = Tenant(fiware_service="openiot", fiware_service_path="/")
        run = AuditRun.create(tenant=tenant, entity_type=None, broker_url="http://orion:1026")
        run.status = RunStatus.COMPLETED
        run.finished_at = datetime.now(timezone.utc)
        run.total_entities_discovered = 5
        repo.runs[(run.id, tenant.fiware_service)] = run
        repo.report_counts[(run.id, tenant.fiware_service)] = 5

        response = await client.get(f"/audits/{run.id}/progress", headers=_TENANT_HEADERS)

        body = response.json()
        assert body["status"] == "completed"
        assert body["processed"] == body["total"] == 5

    @pytest.mark.asyncio
    async def test_unknown_run_id_returns_404(self, client):
        response = await client.get(f"/audits/{uuid4()}/progress", headers=_TENANT_HEADERS)

        assert response.status_code == 404


class TestStreamAuditProgress:
    """Fase 5, secao 4.3 — escopo basico (spec explicito: otimizacao de
    frequencia fica para depois, nao bloqueia o criterio de pronto desta
    fase)."""

    @pytest.mark.asyncio
    async def test_stream_emits_one_event_and_closes_for_a_run_already_in_a_terminal_status(
        self, client, app_and_repo
    ):
        _, repo = app_and_repo
        tenant = Tenant(fiware_service="openiot", fiware_service_path="/")
        run = AuditRun.create(tenant=tenant, entity_type=None, broker_url="http://orion:1026")
        run.status = RunStatus.COMPLETED
        run.finished_at = datetime.now(timezone.utc)
        run.total_entities_discovered = 2
        repo.runs[(run.id, tenant.fiware_service)] = run
        repo.report_counts[(run.id, tenant.fiware_service)] = 2

        response = await client.get(f"/audits/{run.id}/stream", headers=_TENANT_HEADERS)

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        assert '"status": "completed"' in response.text
        assert '"processed": 2' in response.text
        assert '"total": 2' in response.text

    @pytest.mark.asyncio
    async def test_stream_emits_an_error_event_for_an_unknown_run(self, client):
        response = await client.get(f"/audits/{uuid4()}/stream", headers=_TENANT_HEADERS)

        assert response.status_code == 200
        assert "event: error" in response.text
        assert "Audit run not found" in response.text


def _make_summary_view(
    *,
    tenant: Tenant,
    entity_type: EntityType | None = None,
    status: RunStatus = RunStatus.COMPLETED,
    started_at: datetime | None = None,
) -> AuditRunSummaryView:
    """Fase 8, secao 0.1/0.2 -- fabrica minima de AuditRunSummaryView para
    os testes desta secao, evitando repetir os 6 campos de RunSummary em
    cada teste (nenhum deles depende dos contadores em si)."""
    return AuditRunSummaryView(
        id=uuid4(),
        tenant=tenant,
        entity_type=entity_type,
        status=status,
        summary=RunSummary(
            total_entities=1,
            conformant_count=1,
            non_conformant_count=0,
            partial_count=0,
            no_model_count=0,
            schema_unavailable_count=0,
        ),
        started_at=started_at or datetime.now(timezone.utc),
        finished_at=None,
        broker_url="http://orion:1026",
        total_entities_discovered=1,
        failure_reason=None,
    )


class TestListAudits:
    """Fase 8, secao 0.1 -- GET /audits (tela "Audit Runs").

    A secao 0.1 do fase8.spec.md ilustra o filtro com `status=non_conformant`,
    mas isso nao e' um RunStatus valido: RunStatus e' o ciclo de vida do run
    (queued/running/completed/failed/partial, definido na Fase 1 e nunca
    alterado desde entao), nao o ConformanceStatus de uma entidade dentro
    dele (conformant/partial/non_conformant/..., Fase 2) -- confirmado pelo
    proprio exemplo de teste da Fase 3 para RunFilters, que usa
    `RunFilters(status=FAILED)`. Este teste usa "failed" (um RunStatus real)
    para exercitar exatamente o mesmo comportamento -- "o valor da
    querystring chega intacto em RunFilters.status" -- sem depender de um
    valor que a API tipada (status_: RunStatus | None) rejeitaria com 422."""

    @pytest.mark.asyncio
    async def test_status_filter_is_passed_to_the_repository_as_run_filters(self, client, app_and_repo):
        _, repo = app_and_repo
        tenant = Tenant(fiware_service="openiot", fiware_service_path="/")
        repo.run_summaries = [
            _make_summary_view(tenant=tenant, status=RunStatus.FAILED),
            _make_summary_view(tenant=tenant, status=RunStatus.COMPLETED),
        ]

        response = await client.get("/audits?status=failed", headers=_TENANT_HEADERS)

        assert response.status_code == 200
        assert repo.last_list_runs_filters is not None
        assert repo.last_list_runs_filters.status == RunStatus.FAILED
        body = response.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_a_tenant_with_no_runs_returns_an_empty_page_not_404(self, client):
        response = await client.get("/audits", headers=_TENANT_HEADERS)

        assert response.status_code == 200
        body = response.json()
        assert body == {"items": [], "page": 1, "page_size": 20, "total": 0, "has_next": False}


class TestSummaryOverTime:
    """Fase 8, secao 0.2 -- GET /audits/summary-over-time (dados do Dashboard)."""

    @pytest.mark.asyncio
    async def test_returns_summaries_only_for_the_requested_entity_type_and_tenant(
        self, client, app_and_repo
    ):
        _, repo = app_and_repo
        tenant = Tenant(fiware_service="openiot", fiware_service_path="/")
        other_tenant = Tenant(fiware_service="other", fiware_service_path="/")
        matching = _make_summary_view(tenant=tenant, entity_type=EntityType("Streetlight"))
        repo.run_summaries = [
            matching,
            _make_summary_view(tenant=tenant, entity_type=EntityType("AirQualityObserved")),
            _make_summary_view(tenant=other_tenant, entity_type=EntityType("Streetlight")),
        ]

        response = await client.get(
            "/audits/summary-over-time?entity_type=Streetlight", headers=_TENANT_HEADERS
        )

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["id"] == str(matching.id)
        assert body[0]["entity_type"] == "Streetlight"

    @pytest.mark.asyncio
    async def test_route_registration_order_never_shadows_run_id_route(self, client, app_and_repo):
        """Prova por execucao (nao so' por leitura do codigo) do comentario
        de ordenacao no modulo audits.py: /audits/summary-over-time nunca
        deve ser tratado como um {run_id} literal (o que causaria 422 de
        validacao de UUID em vez de rotear para este endpoint)."""
        response = await client.get(
            "/audits/summary-over-time?entity_type=Streetlight", headers=_TENANT_HEADERS
        )

        assert response.status_code != 422


class TestInterpretAuditCommand:
    """Fase 8, secao 0.3 -- POST /audits/interpret (tela "Natural Language")."""

    @pytest.mark.asyncio
    async def test_a_plausible_command_yields_a_plausible_ngsi_entity_type(
        self, client, fake_interpret_use_case
    ):
        fake_interpret_use_case._interpretation = AuditCommandInterpretation(
            entity_type="AirQualityObserved",
            entity_id=None,
            confidence=0.9,
            raw_command="audite os sensores de qualidade do ar",
        )

        response = await client.post(
            "/audits/interpret",
            json={"command_text": "audite os sensores de qualidade do ar"},
            headers=_TENANT_HEADERS,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["entity_type"] == "AirQualityObserved"
        assert body["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_an_ambiguous_command_yields_no_entity_type_and_low_confidence(
        self, client, fake_interpret_use_case
    ):
        fake_interpret_use_case._interpretation = AuditCommandInterpretation(
            entity_type=None, entity_id=None, confidence=0.1, raw_command="faz uma coisa ai"
        )

        response = await client.post(
            "/audits/interpret", json={"command_text": "faz uma coisa ai"}, headers=_TENANT_HEADERS
        )

        assert response.status_code == 200
        body = response.json()
        assert body["entity_type"] is None
        assert body["confidence"] < 0.5

    @pytest.mark.asyncio
    async def test_never_starts_an_audit_run(self, client, fake_interpret_use_case, fake_use_case):
        fake_interpret_use_case._interpretation = AuditCommandInterpretation(
            entity_type="Streetlight", entity_id=None, confidence=0.95, raw_command="x"
        )

        response = await client.post(
            "/audits/interpret", json={"command_text": "audite os postes"}, headers=_TENANT_HEADERS
        )

        assert response.status_code == 200
        assert fake_use_case.started == []
