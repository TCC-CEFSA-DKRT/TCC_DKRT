"""Fase 3 — PostgresAuditRepository + SqlAlchemyUnitOfWork. Ver
.cursor/specs/fase3.spec.md, secoes 2-8.

Requer Docker (testcontainers sobe um Postgres descartavel para os testes).
Nao roda no ambiente de sandbox usado para desenvolver esta fase (sem acesso
a Docker dali, ver relatorio da Fase 3) — rode localmente com:

    pip install -e ".[dev]"
    pytest -m integration tests/integration/persistence/test_postgres_audit_repository.py -v
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from auditor.domain.entities.audit_run import AuditRun, RunStatus
from auditor.domain.entities.entity_report import EntityReport, SchemaOrigin, SchemaSource
from auditor.domain.entities.recommendation import Recommendation, RecommendationAction
from auditor.domain.entities.violation import DetectionSource, Violation, ViolationSeverity
from auditor.domain.errors import InvariantViolationError, RunNotFoundError
from auditor.domain.ports.audit_repository_port import RunFilters
from auditor.domain.value_objects.conformance_status import ConformanceStatus
from auditor.domain.value_objects.data_model_ref import DataModelRef
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.persistence.postgres_audit_repository import PostgresAuditRepository
from auditor.infrastructure.persistence.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
from auditor.infrastructure.persistence.tables import create_all

pytestmark = pytest.mark.integration

TENANT_A = Tenant(fiware_service="smart_city_a", fiware_service_path="/")
TENANT_B = Tenant(fiware_service="smart_city_b", fiware_service_path="/")


@pytest.fixture(scope="module")
def postgres_container():
    with PostgresContainer("pgvector/pgvector:pg16") as container:
        yield container


@pytest.fixture
async def engine(postgres_container):
    sync_url = postgres_container.get_connection_url()  # postgresql+psycopg2://...
    async_url = sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    eng = create_async_engine(async_url)
    await create_all(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
async def connection(engine):
    # Uma transacao por teste, sempre revertida no final (nunca comitada) —
    # e' o que isola os testes uns dos outros dentro do mesmo container/
    # modulo. Sem o rollback explicito, `async with conn.begin():` comita ao
    # sair sem excecao, e os runs de um teste vazam para os seguintes
    # (foi exatamente o que quebrou os testes de ordenacao/cronologia
    # quando rodado pela primeira vez contra Postgres real).
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            yield conn
        finally:
            await trans.rollback()


@pytest.fixture
def repository(connection):
    return PostgresAuditRepository(connection)


def _conformant_report(entity_id: str = "urn:ngsi-ld:Streetlight:001") -> EntityReport:
    return EntityReport(
        entity_id=entity_id,
        entity_type=EntityType("Streetlight"),
        data_model=DataModelRef(
            subject="dataModel.Streetlighting",
            model_name="Streetlight",
            version="latest",
            schema_url="https://raw.githubusercontent.com/smart-data-models/dataModel.Streetlighting/master/Streetlight/schema.json",
        ),
        status=ConformanceStatus.CONFORMANT,
        violations=[],
        recommendations=[],
        schema_origin=SchemaOrigin(source=SchemaSource.LIVE, fetched_at=datetime.now(timezone.utc)),
        semantic_analysis_skipped=True,
        analyzed_at=datetime.now(timezone.utc),
    )


def _partial_report(entity_id: str = "urn:ngsi-ld:Streetlight:002") -> EntityReport:
    return EntityReport(
        entity_id=entity_id,
        entity_type=EntityType("Streetlight"),
        data_model=DataModelRef(
            subject="dataModel.Streetlighting",
            model_name="Streetlight",
            version="latest",
            schema_url="https://raw.githubusercontent.com/smart-data-models/dataModel.Streetlighting/master/Streetlight/schema.json",
        ),
        status=ConformanceStatus.PARTIAL,
        violations=[
            Violation(
                attribute_path="temperature",
                severity=ViolationSeverity.WARNING,
                rule="unexpected_attribute",
                expected=None,
                found="temperature",
                message="Atributo nao esperado pelo schema.",
                detected_by=DetectionSource.STRUCTURAL,
            )
        ],
        recommendations=[
            Recommendation(
                attribute_path="temperature",
                action=RecommendationAction.RENAME_ATTRIBUTE,
                proposed_patch={"from": "temperature", "to": "temp"},
                rationale="Nome mais proximo no schema.",
                confidence=0.7,
            )
        ],
        schema_origin=SchemaOrigin(source=SchemaSource.LIVE, fetched_at=datetime.now(timezone.utc)),
        semantic_analysis_skipped=True,
        analyzed_at=datetime.now(timezone.utc),
    )


def _non_conformant_report(entity_id: str = "urn:ngsi-ld:Streetlight:003") -> EntityReport:
    return EntityReport(
        entity_id=entity_id,
        entity_type=EntityType("Streetlight"),
        data_model=DataModelRef(
            subject="dataModel.Streetlighting",
            model_name="Streetlight",
            version="latest",
            schema_url="https://raw.githubusercontent.com/smart-data-models/dataModel.Streetlighting/master/Streetlight/schema.json",
        ),
        status=ConformanceStatus.NON_CONFORMANT,
        violations=[
            Violation(
                attribute_path="location",
                severity=ViolationSeverity.ERROR,
                rule="missing_required_attribute",
                expected="location",
                found=None,
                message="Atributo obrigatorio ausente.",
                detected_by=DetectionSource.STRUCTURAL,
            )
        ],
        recommendations=[],
        schema_origin=SchemaOrigin(source=SchemaSource.LIVE, fetched_at=datetime.now(timezone.utc)),
        semantic_analysis_skipped=True,
        analyzed_at=datetime.now(timezone.utc),
    )


class TestCreateRunAndGetById:
    @pytest.mark.asyncio
    async def test_create_run_then_get_by_id_returns_empty_run(self, repository):
        run = AuditRun.create(
            tenant=TENANT_A,
            entity_type=EntityType("Streetlight"),
            broker_url="http://orion:1026",
        )
        await repository.create_run(run)

        loaded = await repository.get_by_id(run.id, TENANT_A)

        assert loaded is not None
        assert loaded.id == run.id
        assert loaded.reports == []
        assert loaded.summary.total_entities == 0

    @pytest.mark.asyncio
    async def test_missing_run_returns_none(self, repository):
        assert await repository.get_by_id(uuid4(), TENANT_A) is None


class TestAppendReport:
    @pytest.mark.asyncio
    async def test_three_reports_produce_correct_summary(self, repository):
        run = AuditRun.create(tenant=TENANT_A, entity_type=EntityType("Streetlight"), broker_url="http://orion:1026")
        await repository.create_run(run)

        await repository.append_report(run.id, TENANT_A, _conformant_report())
        await repository.append_report(run.id, TENANT_A, _partial_report())
        await repository.append_report(run.id, TENANT_A, _non_conformant_report())

        loaded = await repository.get_by_id(run.id, TENANT_A)

        assert loaded.summary.total_entities == 3
        assert loaded.summary.conformant_count == 1
        assert loaded.summary.partial_count == 1
        assert loaded.summary.non_conformant_count == 1
        assert len(loaded.reports) == 3

    @pytest.mark.asyncio
    async def test_append_report_to_unknown_run_raises(self, repository):
        with pytest.raises(RunNotFoundError):
            await repository.append_report(uuid4(), TENANT_A, _conformant_report())

    @pytest.mark.asyncio
    async def test_reentry_of_same_entity_does_not_duplicate(self, repository):
        run = AuditRun.create(tenant=TENANT_A, entity_type=EntityType("Streetlight"), broker_url="http://orion:1026")
        await repository.create_run(run)
        report = _conformant_report(entity_id="urn:ngsi-ld:Streetlight:dup")

        await repository.append_report(run.id, TENANT_A, report)
        await repository.append_report(run.id, TENANT_A, report)  # reentrega simulada

        loaded = await repository.get_by_id(run.id, TENANT_A)
        assert len(loaded.reports) == 1
        assert loaded.summary.total_entities == 1
        assert loaded.summary.conformant_count == 1

    @pytest.mark.asyncio
    async def test_reentry_with_different_status_adjusts_counters_correctly(self, repository):
        run = AuditRun.create(tenant=TENANT_A, entity_type=EntityType("Streetlight"), broker_url="http://orion:1026")
        await repository.create_run(run)
        entity_id = "urn:ngsi-ld:Streetlight:flip"

        await repository.append_report(run.id, TENANT_A, _conformant_report(entity_id=entity_id))
        await repository.append_report(run.id, TENANT_A, _non_conformant_report(entity_id=entity_id))

        loaded = await repository.get_by_id(run.id, TENANT_A)
        assert len(loaded.reports) == 1
        assert loaded.summary.total_entities == 1
        assert loaded.summary.conformant_count == 0
        assert loaded.summary.non_conformant_count == 1
        assert loaded.reports[0].status == ConformanceStatus.NON_CONFORMANT


class TestUpdateRunStatus:
    @pytest.mark.asyncio
    async def test_completed_with_finished_at_is_reflected(self, repository):
        run = AuditRun.create(tenant=TENANT_A, entity_type=EntityType("Streetlight"), broker_url="http://orion:1026")
        await repository.create_run(run)
        finished_at = datetime.now(timezone.utc)

        await repository.update_run_status(run.id, TENANT_A, RunStatus.COMPLETED, finished_at=finished_at)

        loaded = await repository.get_by_id(run.id, TENANT_A)
        assert loaded.status == RunStatus.COMPLETED
        assert loaded.finished_at is not None

    @pytest.mark.asyncio
    async def test_completed_without_finished_at_raises(self, repository):
        run = AuditRun.create(tenant=TENANT_A, entity_type=EntityType("Streetlight"), broker_url="http://orion:1026")
        await repository.create_run(run)

        with pytest.raises(InvariantViolationError):
            await repository.update_run_status(run.id, TENANT_A, RunStatus.COMPLETED, finished_at=None)

    @pytest.mark.asyncio
    async def test_unknown_run_raises_run_not_found(self, repository):
        with pytest.raises(RunNotFoundError):
            await repository.update_run_status(uuid4(), TENANT_A, RunStatus.FAILED)


class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_get_by_id_hides_other_tenants_run(self, repository):
        run = AuditRun.create(tenant=TENANT_A, entity_type=EntityType("Streetlight"), broker_url="http://orion:1026")
        await repository.create_run(run)

        assert await repository.get_by_id(run.id, TENANT_B) is None
        assert await repository.get_by_id(run.id, TENANT_A) is not None

    @pytest.mark.asyncio
    async def test_list_runs_excludes_other_tenants(self, repository):
        run_a = AuditRun.create(tenant=TENANT_A, entity_type=EntityType("Streetlight"), broker_url="http://orion:1026")
        run_b = AuditRun.create(tenant=TENANT_B, entity_type=EntityType("Streetlight"), broker_url="http://orion:1026")
        await repository.create_run(run_a)
        await repository.create_run(run_b)

        page = await repository.list_runs(TENANT_B, RunFilters())

        ids = {item.id for item in page.items}
        assert run_b.id in ids
        assert run_a.id not in ids


class TestListRunsFiltersAndPagination:
    @pytest.mark.asyncio
    async def test_pagination_has_next(self, repository):
        base_time = datetime.now(timezone.utc)
        for i in range(25):
            run = AuditRun.create(
                tenant=TENANT_A,
                entity_type=EntityType("Streetlight"),
                broker_url="http://orion:1026",
                started_at=base_time + timedelta(seconds=i),
            )
            await repository.create_run(run)

        page = await repository.list_runs(TENANT_A, RunFilters(page=1, page_size=20))

        assert len(page.items) == 20
        assert page.has_next is True

    @pytest.mark.asyncio
    async def test_status_filter(self, repository):
        run_queued = AuditRun.create(tenant=TENANT_A, entity_type=EntityType("Streetlight"), broker_url="http://orion:1026")
        run_failed = AuditRun.create(tenant=TENANT_A, entity_type=EntityType("Streetlight"), broker_url="http://orion:1026")
        await repository.create_run(run_queued)
        await repository.create_run(run_failed)
        await repository.update_run_status(run_failed.id, TENANT_A, RunStatus.FAILED)

        page = await repository.list_runs(TENANT_A, RunFilters(status=RunStatus.FAILED))

        ids = {item.id for item in page.items}
        assert run_failed.id in ids
        assert run_queued.id not in ids

    @pytest.mark.asyncio
    async def test_default_order_is_started_at_descending(self, repository):
        base_time = datetime.now(timezone.utc)
        older = AuditRun.create(
            tenant=TENANT_A, entity_type=EntityType("Streetlight"), broker_url="http://orion:1026",
            started_at=base_time,
        )
        newer = AuditRun.create(
            tenant=TENANT_A, entity_type=EntityType("Streetlight"), broker_url="http://orion:1026",
            started_at=base_time + timedelta(minutes=5),
        )
        await repository.create_run(older)
        await repository.create_run(newer)

        page = await repository.list_runs(TENANT_A, RunFilters(page_size=2))

        assert page.items[0].id == newer.id
        assert page.items[1].id == older.id


class TestListRunSummariesOverTime:
    @pytest.mark.asyncio
    async def test_returns_chronological_order(self, repository):
        base_time = datetime.now(timezone.utc)
        expected_order = []
        for i in range(5):
            run = AuditRun.create(
                tenant=TENANT_A,
                entity_type=EntityType("Streetlight"),
                broker_url="http://orion:1026",
                started_at=base_time + timedelta(minutes=i),
            )
            await repository.create_run(run)
            expected_order.append(run.id)

        summaries = await repository.list_run_summaries_over_time(TENANT_A, EntityType("Streetlight"))

        assert [s.id for s in summaries] == expected_order


class TestUnitOfWork:
    @pytest.mark.asyncio
    async def test_rollback_on_exception_persists_nothing(self, engine):
        run = AuditRun.create(tenant=TENANT_A, entity_type=EntityType("Streetlight"), broker_url="http://orion:1026")

        with pytest.raises(RuntimeError):
            async with SqlAlchemyUnitOfWork(engine) as uow:
                await uow.audits.create_run(run)
                raise RuntimeError("falha proposital no meio do bloco")

        async with engine.connect() as conn:
            check_repo = PostgresAuditRepository(conn)
            assert await check_repo.get_by_id(run.id, TENANT_A) is None

    @pytest.mark.asyncio
    async def test_commit_on_success_is_visible_outside_the_block(self, engine):
        run = AuditRun.create(tenant=TENANT_A, entity_type=EntityType("Streetlight"), broker_url="http://orion:1026")

        async with SqlAlchemyUnitOfWork(engine) as uow:
            await uow.audits.create_run(run)

        async with engine.connect() as conn:
            check_repo = PostgresAuditRepository(conn)
            loaded = await check_repo.get_by_id(run.id, TENANT_A)
            assert loaded is not None


class TestRoundTripMapping:
    @pytest.mark.asyncio
    async def test_full_report_round_trips_through_all_fields(self, repository):
        run = AuditRun.create(tenant=TENANT_A, entity_type=EntityType("Streetlight"), broker_url="http://orion:1026")
        await repository.create_run(run)
        report = _partial_report()

        await repository.append_report(run.id, TENANT_A, report)

        loaded = await repository.get_by_id(run.id, TENANT_A)
        loaded_report = loaded.reports[0]

        assert loaded_report.entity_id == report.entity_id
        assert loaded_report.entity_type == report.entity_type
        assert loaded_report.data_model == report.data_model
        assert loaded_report.status == report.status
        assert len(loaded_report.violations) == 1
        assert loaded_report.violations[0].attribute_path == "temperature"
        assert len(loaded_report.recommendations) == 1
        assert loaded_report.recommendations[0].proposed_patch == {"from": "temperature", "to": "temp"}
        assert loaded_report.schema_origin.source == SchemaSource.LIVE
