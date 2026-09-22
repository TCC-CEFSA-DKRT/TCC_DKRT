"""Fase 4 — RunAuditUseCase. Ver .cursor/specs/fase4.spec.md, secao 3.
Fase 5 — start()/process()/mark_failed(). Ver .cursor/specs/fase5.spec.md,
secao 5.

Fakes de todos os ports (ContextBrokerPort, SchemaCatalogPort, UnitOfWork,
JobQueuePort) — mesmo padrao de test double usado nas Fases 1-3, sem Orion
nem Postgres reais aqui.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from auditor.application.use_cases.run_audit import RunAuditUseCase
from auditor.domain.entities.audit_job import AuditJob
from auditor.domain.entities.audit_run import AuditRun, RunStatus, RunSummary
from auditor.domain.entities.entity_report import (
    EntityReport,
    InferenceBackend,
    SchemaOrigin,
    SchemaSource,
    SemanticAnalysisUsage,
)
from auditor.domain.entities.violation import (
    DetectionSource,
    Violation,
    ViolationSeverity,
)
from auditor.domain.errors import (
    ContextBrokerUnavailableError,
    RunNotFoundError,
    SchemaUnavailableError,
)
from auditor.domain.ports.schema_catalog_port import ResolvedSchema
from auditor.domain.ports.semantic_analyzer_port import SemanticAnalysisResult
from auditor.domain.services.structural_validator import StructuralValidator
from auditor.domain.value_objects.conformance_status import ConformanceStatus
from auditor.domain.value_objects.data_model_ref import DataModelRef
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.context_broker.ngsi_v2_mapper import NgsiV2Mapper

_TENANT = Tenant(fiware_service="openiot", fiware_service_path="/")
_NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)

_SCHEMA = {
    "required": ["id", "type", "illuminanceLevel"],
    "additionalProperties": True,
    "properties": {
        "id": {"type": "string"},
        "type": {"type": "string"},
        "illuminanceLevel": {"type": "number"},
    },
}
_DATA_MODEL = DataModelRef(
    subject="dataModel.Streetlighting",
    model_name="Streetlight",
    version="latest",
    schema_url="https://example.org/schema.json",
)


def _attr(value):
    return {"type": "Number", "value": value, "metadata": {}}


def _raw_entity(entity_id: str, entity_type: str = "Streetlight", **attrs) -> dict:
    raw = {"id": entity_id, "type": entity_type}
    for key, value in attrs.items():
        raw[key] = _attr(value)
    return raw


class _FakeContextBroker:
    def __init__(self, entities=None, error: Exception | None = None):
        self._entities = entities or []
        self._error = error

    async def fetch_entities(self, tenant, entity_type, entity_id=None):
        if self._error is not None:
            raise self._error
        return self._entities


class _FakeSchemaCatalog:
    """resolve_data_model/fetch_schema configuraveis por entity_type, mais
    um gatilho opcional de falha inesperada numa chamada especifica (para
    simular infra caindo no meio do lote — secao 3.3 do spec)."""

    def __init__(self, data_model=_DATA_MODEL, schema_content=_SCHEMA,
                 unavailable_for: set[str] | None = None,
                 no_model_for: set[str] | None = None,
                 raise_unexpected_on_call: int | None = None):
        self._data_model = data_model
        self._schema_content = schema_content
        self._unavailable_for = unavailable_for or set()
        self._no_model_for = no_model_for or set()
        self._raise_unexpected_on_call = raise_unexpected_on_call
        self.resolve_calls = 0

    async def resolve_data_model(self, entity_type):
        self.resolve_calls += 1
        if self._raise_unexpected_on_call == self.resolve_calls:
            raise RuntimeError("falha inesperada de infraestrutura")
        if entity_type.value in self._no_model_for:
            return None
        return self._data_model

    async def fetch_schema(self, data_model):
        if data_model.model_name in self._unavailable_for:
            raise SchemaUnavailableError("schema indisponivel agora")
        return ResolvedSchema(
            data_model=data_model,
            content=self._schema_content,
            origin=SchemaOrigin(source=SchemaSource.LIVE, fetched_at=_NOW),
        )


class _FakeAuditRepository:
    def __init__(self):
        self.runs: dict[UUID, AuditRun] = {}
        self.append_calls = 0

    async def create_run(self, run: AuditRun) -> None:
        self.runs[run.id] = run

    async def append_report(self, run_id, tenant, report: EntityReport) -> None:
        self.append_calls += 1
        run = self.runs.get(run_id)
        if run is None or run.tenant != tenant:
            raise RunNotFoundError(str(run_id))
        existing_idx = next(
            (i for i, r in enumerate(run.reports) if r.entity_id == report.entity_id), None
        )
        if existing_idx is not None:
            run.reports[existing_idx] = report
            run.summary = RunSummary.from_reports(run.reports)
        else:
            run.add_report(report)

    async def update_run_status(self, run_id, tenant, status, finished_at=None, failure_reason=None) -> None:
        run = self.runs.get(run_id)
        if run is None or run.tenant != tenant:
            raise RunNotFoundError(str(run_id))
        run.status = status
        run.finished_at = finished_at
        run.failure_reason = failure_reason

    async def set_total_entities(self, run_id, tenant, total: int) -> None:
        run = self.runs.get(run_id)
        if run is None or run.tenant != tenant:
            raise RunNotFoundError(str(run_id))
        run.total_entities_discovered = total

    async def count_reports(self, run_id, tenant) -> int:
        run = self.runs.get(run_id)
        if run is None or run.tenant != tenant:
            raise RunNotFoundError(str(run_id))
        return len(run.reports)

    async def get_by_id(self, run_id, tenant):
        run = self.runs.get(run_id)
        if run is None or run.tenant != tenant:
            return None
        return run


class _FakeUnitOfWork:
    def __init__(self, repository: _FakeAuditRepository):
        self.audits = repository

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None


class _FakeJobQueue:
    def __init__(self):
        self.enqueued: list[AuditJob] = []

    async def enqueue(self, job: AuditJob) -> None:
        self.enqueued.append(job)

    def consume(self):
        raise NotImplementedError("nao usado nestes testes — ver test_audit_worker.py")

    def consume_dead_letters(self):
        raise NotImplementedError("nao usado nestes testes — ver test_audit_worker.py")


class _FakeKnowledgeRetriever:
    """Fase 7 — no-op por padrao (retrieve() devolve []); passe
    `should_not_be_called=True` para transformar qualquer chamada em
    AssertionError (secao 4.1, ultimo caso: prova de que CONFORMANT/
    NO_MODEL_FOUND nunca acionam o Nivel 2)."""

    def __init__(self, should_not_be_called: bool = False):
        self._should_not_be_called = should_not_be_called
        self.calls: list[str] = []

    async def retrieve(self, query: str, *, top_k: int = 5):
        if self._should_not_be_called:
            raise AssertionError("KnowledgeRetrieverPort.retrieve() nao deveria ter sido chamado")
        self.calls.append(query)
        return []


class _FakeSemanticAnalyzer:
    """Fase 7 — no-op por padrao (analyze() devolve um SemanticAnalysisResult
    vazio, ou seja, "nada encontrado", nunca muda o status/violacoes do
    Nivel 1). Passe `result=...` para simular achados/indisponibilidade
    especificos, ou `should_not_be_called=True` (mesmo espirito do fake
    acima)."""

    def __init__(
        self,
        result: SemanticAnalysisResult | None = None,
        should_not_be_called: bool = False,
    ):
        self._result = result if result is not None else SemanticAnalysisResult()
        self._should_not_be_called = should_not_be_called
        self.calls = 0

    async def analyze(self, ctx):
        if self._should_not_be_called:
            raise AssertionError("SemanticAnalyzerPort.analyze() nao deveria ter sido chamado")
        self.calls += 1
        return self._result


class _SteppingClock:
    """Fase 10 — clock de teste que avanca um passo fixo a cada chamada,
    em vez do `lambda: _NOW` constante usado no resto do arquivo. Constante
    produziria sempre duracao 0.0 (suficiente para os outros testes, que
    nao se importam com o campo); este avanca de proposito para provar que
    `processing_duration_seconds` de fato usa `self._clock()`, nao um
    relogio de parede separado."""

    def __init__(self, start: datetime, step_seconds: float = 1.0):
        self._next = start
        self._step = timedelta(seconds=step_seconds)

    def __call__(self) -> datetime:
        value = self._next
        self._next = self._next + self._step
        return value


def _make_use_case(
    context_broker,
    schema_catalog,
    repository=None,
    job_queue=None,
    knowledge_retriever=None,
    semantic_analyzer=None,
    clock=None,
):
    repository = repository or _FakeAuditRepository()
    uow = _FakeUnitOfWork(repository)
    # Fase 7: fakes no-op por padrao (nunca None) — assim toda entidade
    # NON_CONFORMANT/PARTIAL produzida pelos testes de Fase 4/5 (que nao
    # sabem nada sobre Nivel 2) continua funcionando sem alteracao, ja'
    # que os no-ops nao adicionam violacao/recomendacao nenhuma.
    knowledge_retriever = knowledge_retriever or _FakeKnowledgeRetriever()
    semantic_analyzer = semantic_analyzer or _FakeSemanticAnalyzer()
    use_case = RunAuditUseCase(
        context_broker=context_broker,
        schema_catalog=schema_catalog,
        validator=StructuralValidator(),
        mapper=NgsiV2Mapper(),
        uow=uow,
        broker_url="http://orion:1026",
        clock=clock or (lambda: _NOW),
        job_queue=job_queue,
        knowledge_retriever=knowledge_retriever,
        semantic_analyzer=semantic_analyzer,
    )
    return use_case, repository


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_three_conformant_entities_complete_the_run(self):
        entities = [
            _raw_entity("urn:1", illuminanceLevel=0.5),
            _raw_entity("urn:2", illuminanceLevel=0.6),
            _raw_entity("urn:3", illuminanceLevel=0.7),
        ]
        use_case, repo = _make_use_case(
            _FakeContextBroker(entities), _FakeSchemaCatalog()
        )

        run_id = await use_case.execute(_TENANT, EntityType("Streetlight"))
        run = await repo.get_by_id(run_id, _TENANT)

        assert run.status == RunStatus.COMPLETED
        assert run.summary.total_entities == 3
        assert run.summary.conformant_count == 3

    @pytest.mark.asyncio
    async def test_mixed_statuses_are_counted_correctly(self):
        entities = [
            _raw_entity("urn:conformant", illuminanceLevel=0.5),
            _raw_entity("urn:missing-required"),  # falta illuminanceLevel -> NON_CONFORMANT
        ]
        use_case, repo = _make_use_case(
            _FakeContextBroker(entities), _FakeSchemaCatalog()
        )

        run_id = await use_case.execute(_TENANT, EntityType("Streetlight"))
        run = await repo.get_by_id(run_id, _TENANT)

        assert run.status == RunStatus.COMPLETED
        assert run.summary.total_entities == 2
        assert run.summary.conformant_count == 1
        assert run.summary.non_conformant_count == 1


class TestResilience:
    @pytest.mark.asyncio
    async def test_one_malformed_entity_does_not_fail_the_batch(self):
        entities = [_raw_entity(f"urn:{i}", illuminanceLevel=0.5) for i in range(9)]
        entities.append({"id": "urn:bad", "type": "Streetlight", "illuminanceLevel": 0.5})  # sem envelope
        use_case, repo = _make_use_case(
            _FakeContextBroker(entities), _FakeSchemaCatalog()
        )

        run_id = await use_case.execute(_TENANT, EntityType("Streetlight"))
        run = await repo.get_by_id(run_id, _TENANT)

        assert run.status == RunStatus.COMPLETED
        assert run.summary.total_entities == 10
        bad_report = next(r for r in run.reports if r.entity_id == "urn:bad")
        assert bad_report.status == ConformanceStatus.NON_CONFORMANT
        assert bad_report.violations[0].rule == "malformed_attribute"
        assert bad_report.violations[0].severity.value == "error"

    @pytest.mark.asyncio
    async def test_no_data_model_for_type_completes_normally(self):
        entities = [_raw_entity("urn:1", entity_type="UnknownType")]
        use_case, repo = _make_use_case(
            _FakeContextBroker(entities),
            _FakeSchemaCatalog(no_model_for={"UnknownType"}),
        )

        run_id = await use_case.execute(_TENANT, EntityType("UnknownType"))
        run = await repo.get_by_id(run_id, _TENANT)

        assert run.status == RunStatus.COMPLETED
        assert run.reports[0].status == ConformanceStatus.NO_MODEL_FOUND
        assert run.reports[0].data_model is None

    @pytest.mark.asyncio
    async def test_schema_unavailable_for_one_entity_others_continue(self):
        entities = [
            _raw_entity("urn:ok", illuminanceLevel=0.5),
            _raw_entity("urn:unavailable", illuminanceLevel=0.5),
        ]
        catalog = _FakeSchemaCatalog(unavailable_for=set())
        # torna o schema indisponivel so' para a segunda chamada de fetch_schema
        original_fetch = catalog.fetch_schema
        call_count = {"n": 0}

        async def fetch_schema(data_model):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise SchemaUnavailableError("indisponivel")
            return await original_fetch(data_model)

        catalog.fetch_schema = fetch_schema  # type: ignore[method-assign]

        use_case, repo = _make_use_case(_FakeContextBroker(entities), catalog)

        run_id = await use_case.execute(_TENANT, EntityType("Streetlight"))
        run = await repo.get_by_id(run_id, _TENANT)

        assert run.status == RunStatus.COMPLETED
        statuses = {r.entity_id: r.status for r in run.reports}
        assert statuses["urn:ok"] == ConformanceStatus.CONFORMANT
        assert statuses["urn:unavailable"] == ConformanceStatus.SCHEMA_UNAVAILABLE


class TestInfrastructureFailures:
    @pytest.mark.asyncio
    async def test_context_broker_unavailable_before_any_entity_marks_run_failed(self):
        use_case, repo = _make_use_case(
            _FakeContextBroker(error=ContextBrokerUnavailableError("orion fora do ar")),
            _FakeSchemaCatalog(),
        )

        run_id = await use_case.execute(_TENANT, EntityType("Streetlight"))
        run = await repo.get_by_id(run_id, _TENANT)

        assert run.status == RunStatus.FAILED
        assert run.summary.total_entities == 0

    @pytest.mark.asyncio
    async def test_unexpected_failure_mid_batch_marks_run_partial_and_keeps_processed_reports(self):
        entities = [_raw_entity(f"urn:{i}", illuminanceLevel=0.5) for i in range(10)]
        # a 6a chamada a resolve_data_model (entidade urn:5, indice 5) falha
        # de forma inesperada — simula "conexao caiu no meio do processamento"
        catalog = _FakeSchemaCatalog(raise_unexpected_on_call=6)
        use_case, repo = _make_use_case(_FakeContextBroker(entities), catalog)

        run_id = await use_case.execute(_TENANT, EntityType("Streetlight"))
        run = await repo.get_by_id(run_id, _TENANT)

        assert run.status == RunStatus.PARTIAL
        assert run.summary.total_entities == 5
        assert {r.entity_id for r in run.reports} == {f"urn:{i}" for i in range(5)}


class TestStart:
    """Fase 5, secao 5: start() cria o run e publica o job — nao processa
    nada, e' O(1) independente do numero de entidades."""

    @pytest.mark.asyncio
    async def test_start_creates_run_and_enqueues_job_without_processing(self):
        queue = _FakeJobQueue()
        # ContextBrokerPort nunca deveria ser chamado por start() — se
        # fosse, este erro estouraria e o teste falharia.
        broker = _FakeContextBroker(error=AssertionError("start() nao deveria consultar o broker"))
        use_case, repo = _make_use_case(broker, _FakeSchemaCatalog(), job_queue=queue)

        run_id = await use_case.start(_TENANT, EntityType("Streetlight"), "urn:1")

        run = await repo.get_by_id(run_id, _TENANT)
        assert run.status == RunStatus.QUEUED
        assert run.summary.total_entities == 0

        assert len(queue.enqueued) == 1
        job = queue.enqueued[0]
        assert job.run_id == run_id
        assert job.tenant == _TENANT
        assert job.entity_type == EntityType("Streetlight")
        assert job.entity_id == "urn:1"

    @pytest.mark.asyncio
    async def test_start_without_job_queue_configured_raises(self):
        use_case, _ = _make_use_case(_FakeContextBroker([]), _FakeSchemaCatalog(), job_queue=None)

        with pytest.raises(RuntimeError):
            await use_case.start(_TENANT, EntityType("Streetlight"))


class TestProcess:
    """Fase 5, secao 5: process() e' a versao usada pelo AuditWorker — ao
    contrario de process_run(), NAO captura falha de infraestrutura (deixa
    propagar para o worker decidir nack/DLQ) e reprocessa tudo do zero a
    cada chamada (idempotente por (run_id, entity_id) desde a Fase 3)."""

    @pytest.mark.asyncio
    async def test_process_runs_a_created_run_to_completion(self):
        entities = [
            _raw_entity("urn:1", illuminanceLevel=0.5),
            _raw_entity("urn:2", illuminanceLevel=0.6),
        ]
        use_case, repo = _make_use_case(_FakeContextBroker(entities), _FakeSchemaCatalog())
        run = await use_case.create_run(_TENANT, EntityType("Streetlight"))

        await use_case.process(run.id, _TENANT, EntityType("Streetlight"))

        persisted = await repo.get_by_id(run.id, _TENANT)
        assert persisted.status == RunStatus.COMPLETED
        assert persisted.total_entities_discovered == 2
        assert persisted.summary.total_entities == 2
        assert persisted.finished_at is not None

    @pytest.mark.asyncio
    async def test_process_propagates_context_broker_failure_instead_of_swallowing_it(self):
        use_case, repo = _make_use_case(
            _FakeContextBroker(error=ContextBrokerUnavailableError("orion fora do ar")),
            _FakeSchemaCatalog(),
        )
        run = await use_case.create_run(_TENANT, EntityType("Streetlight"))

        with pytest.raises(ContextBrokerUnavailableError):
            await use_case.process(run.id, _TENANT, EntityType("Streetlight"))

        # Diferente de process_run(): a excecao propagou sem marcar o run
        # como FAILED sozinho — quem decide o que fazer com a falha e' o
        # AuditWorker (nack -> reentrega/DLQ), nao o use case.
        persisted = await repo.get_by_id(run.id, _TENANT)
        assert persisted.status == RunStatus.RUNNING

    @pytest.mark.asyncio
    async def test_process_propagates_unexpected_mid_batch_failure(self):
        entities = [_raw_entity(f"urn:{i}", illuminanceLevel=0.5) for i in range(10)]
        catalog = _FakeSchemaCatalog(raise_unexpected_on_call=6)
        use_case, repo = _make_use_case(_FakeContextBroker(entities), catalog)
        run = await use_case.create_run(_TENANT, EntityType("Streetlight"))

        with pytest.raises(RuntimeError):
            await use_case.process(run.id, _TENANT, EntityType("Streetlight"))

        persisted = await repo.get_by_id(run.id, _TENANT)
        # o que ja' foi persistido nas iteracoes anteriores fica — so' nao
        # ha' status terminal ainda, porque a excecao propagou antes disso.
        assert persisted.status == RunStatus.RUNNING
        assert persisted.summary.total_entities == 5

    @pytest.mark.asyncio
    async def test_reprocessing_after_partial_failure_produces_exact_report_count_without_duplication(self):
        """Fase 5, secao 3.1, terceiro caso de teste: job reentregue apos
        falha parcial (5 de 10 ja' persistidas na tentativa anterior) —
        reprocessar o run inteiro do zero da' exatamente 10 EntityReport,
        nunca 15, nunca duplicado."""
        entities = [_raw_entity(f"urn:{i}", illuminanceLevel=0.5) for i in range(10)]
        failing_catalog = _FakeSchemaCatalog(raise_unexpected_on_call=6)
        use_case, repo = _make_use_case(_FakeContextBroker(entities), failing_catalog)
        run = await use_case.create_run(_TENANT, EntityType("Streetlight"))

        with pytest.raises(RuntimeError):
            await use_case.process(run.id, _TENANT, EntityType("Streetlight"))
        assert repo.runs[run.id].summary.total_entities == 5

        # "reentrega": mesmo run_id, desta vez sem falha simulada.
        use_case._schema_catalog = _FakeSchemaCatalog()
        await use_case.process(run.id, _TENANT, EntityType("Streetlight"))

        persisted = await repo.get_by_id(run.id, _TENANT)
        assert persisted.status == RunStatus.COMPLETED
        assert persisted.summary.total_entities == 10
        assert len(persisted.reports) == 10
        assert {r.entity_id for r in persisted.reports} == {f"urn:{i}" for i in range(10)}


class TestMarkFailed:
    @pytest.mark.asyncio
    async def test_mark_failed_sets_failed_status_with_reason(self):
        use_case, repo = _make_use_case(_FakeContextBroker([]), _FakeSchemaCatalog())
        run = await use_case.create_run(_TENANT, EntityType("Streetlight"))

        await use_case.mark_failed(run.id, _TENANT, reason="max_retries_exceeded")

        persisted = await repo.get_by_id(run.id, _TENANT)
        assert persisted.status == RunStatus.FAILED
        assert persisted.failure_reason == "max_retries_exceeded"
        assert persisted.finished_at is not None


_PARTIAL_SCHEMA = {
    **_SCHEMA,
    "additionalProperties": False,
}

_SEMANTIC_ERROR_VIOLATION = Violation(
    attribute_path="temperature",
    severity=ViolationSeverity.ERROR,
    rule="attribute_name_synonym",
    expected="temperature",
    found="temp",
    message="'temp' parece ser 'temperature' com nome errado.",
    detected_by=DetectionSource.SEMANTIC,
)


class TestSemanticAnalysisTriggering:
    """Fase 7, secao 3.1, REVISADA pela ADR-0014: o Nivel 2 passou a rodar
    sobre toda entidade em que o Nivel 1 resolveu um schema — inclusive
    CONFORMANT — nao mais so' NON_CONFORMANT/PARTIAL. So' NO_MODEL_FOUND/
    SCHEMA_UNAVAILABLE (sem schema, sem plain_values coerentes) continuam
    sem acionar `SemanticAnalyzerPort.analyze()`."""

    @pytest.mark.asyncio
    async def test_every_entity_with_a_resolved_schema_calls_analyze_regardless_of_structural_status(self):
        conformant = [_raw_entity(f"urn:c{i}", illuminanceLevel=0.5) for i in range(900)]
        non_conformant = [_raw_entity(f"urn:nc{i}") for i in range(100)]  # falta illuminanceLevel
        entities = conformant + non_conformant
        semantic_analyzer = _FakeSemanticAnalyzer()
        use_case, repo = _make_use_case(
            _FakeContextBroker(entities),
            _FakeSchemaCatalog(),
            semantic_analyzer=semantic_analyzer,
        )

        run_id = await use_case.execute(_TENANT, EntityType("Streetlight"))
        run = await repo.get_by_id(run_id, _TENANT)

        assert run.summary.total_entities == 1000
        # ADR-0014: os 900 CONFORMANT agora chamam analyze() tambem — nao
        # mais so' os 100 NON_CONFORMANT (comportamento antigo, invertido
        # de proposito por este teste).
        assert semantic_analyzer.calls == 1000

    @pytest.mark.asyncio
    async def test_no_model_found_entity_never_calls_analyze(self):
        entities = [_raw_entity("urn:1", entity_type="UnknownType")]
        use_case, repo = _make_use_case(
            _FakeContextBroker(entities),
            _FakeSchemaCatalog(no_model_for={"UnknownType"}),
            semantic_analyzer=_FakeSemanticAnalyzer(should_not_be_called=True),
            knowledge_retriever=_FakeKnowledgeRetriever(should_not_be_called=True),
        )

        run_id = await use_case.execute(_TENANT, EntityType("UnknownType"))
        run = await repo.get_by_id(run_id, _TENANT)

        assert run.status == RunStatus.COMPLETED
        report = run.reports[0]
        assert report.status == ConformanceStatus.NO_MODEL_FOUND
        assert report.semantic_analysis_skipped is True

    @pytest.mark.asyncio
    async def test_conformant_entity_now_calls_analyze_for_an_independent_semantic_check(self):
        # ADR-0014: uma entidade que passa 100% no Nivel 1 (nenhuma
        # violacao estrutural, nem o atributo extra invisivel ao schema
        # permissivo) e' exatamente o caso que a regra antiga deixava fora
        # do Nivel 2 — e exatamente o caso que este teste agora prova que
        # E' examinado.
        entity = _raw_entity("urn:1", illuminanceLevel=0.5, extraAttribute="qualquer coisa")
        semantic_analyzer = _FakeSemanticAnalyzer()
        knowledge_retriever = _FakeKnowledgeRetriever()
        use_case, repo = _make_use_case(
            _FakeContextBroker([entity]),
            _FakeSchemaCatalog(),
            semantic_analyzer=semantic_analyzer,
            knowledge_retriever=knowledge_retriever,
        )

        run_id = await use_case.execute(_TENANT, EntityType("Streetlight"))
        run = await repo.get_by_id(run_id, _TENANT)

        report = run.reports[0]
        assert report.status == ConformanceStatus.CONFORMANT
        assert report.semantic_analysis_skipped is False
        assert semantic_analyzer.calls == 1
        # sem violacao estrutural para descrever, a query do RAG cai no
        # fallback generico (ver _semantic_query_from) em vez de ficar vazia.
        assert knowledge_retriever.calls == ["verificacao semantica geral de Streetlight"]


class TestSemanticAnalysisIntegration:
    """Fase 7, secao 4.1 — integracao ao `_build_report`."""

    @pytest.mark.asyncio
    async def test_non_conformant_entity_gets_semantic_violation_appended_status_unchanged(self):
        entity = _raw_entity("urn:1")  # falta illuminanceLevel -> NON_CONFORMANT (Nivel 1)
        semantic_analyzer = _FakeSemanticAnalyzer(
            result=SemanticAnalysisResult(violations=(_SEMANTIC_ERROR_VIOLATION,))
        )
        use_case, repo = _make_use_case(
            _FakeContextBroker([entity]),
            _FakeSchemaCatalog(),
            semantic_analyzer=semantic_analyzer,
        )

        run_id = await use_case.execute(_TENANT, EntityType("Streetlight"))
        run = await repo.get_by_id(run_id, _TENANT)

        report = run.reports[0]
        assert report.status == ConformanceStatus.NON_CONFORMANT
        assert len(report.violations) == 2
        assert any(v.detected_by == DetectionSource.SEMANTIC for v in report.violations)
        assert report.semantic_analysis_skipped is False

    @pytest.mark.asyncio
    async def test_partial_entity_upgraded_to_non_conformant_by_semantic_error_violation(self):
        # additionalProperties=False + atributo extra -> unico achado do
        # Nivel 1 e' WARNING (unexpected_property) -> PARTIAL.
        entity = _raw_entity("urn:1", illuminanceLevel=0.5, extraAttribute="x")
        semantic_analyzer = _FakeSemanticAnalyzer(
            result=SemanticAnalysisResult(violations=(_SEMANTIC_ERROR_VIOLATION,))
        )
        use_case, repo = _make_use_case(
            _FakeContextBroker([entity]),
            _FakeSchemaCatalog(schema_content=_PARTIAL_SCHEMA),
            semantic_analyzer=semantic_analyzer,
        )

        run_id = await use_case.execute(_TENANT, EntityType("Streetlight"))
        run = await repo.get_by_id(run_id, _TENANT)

        report = run.reports[0]
        assert report.status == ConformanceStatus.NON_CONFORMANT
        assert report.semantic_analysis_skipped is False

    @pytest.mark.asyncio
    async def test_analysis_unavailable_keeps_only_level_one_violations_and_does_not_fail_run(self):
        entity = _raw_entity("urn:1")  # falta illuminanceLevel -> NON_CONFORMANT (Nivel 1)
        semantic_analyzer = _FakeSemanticAnalyzer(
            result=SemanticAnalysisResult(analysis_unavailable=True)
        )
        use_case, repo = _make_use_case(
            _FakeContextBroker([entity]),
            _FakeSchemaCatalog(),
            semantic_analyzer=semantic_analyzer,
        )

        run_id = await use_case.execute(_TENANT, EntityType("Streetlight"))
        run = await repo.get_by_id(run_id, _TENANT)

        assert run.status == RunStatus.COMPLETED
        report = run.reports[0]
        assert report.status == ConformanceStatus.NON_CONFORMANT
        assert len(report.violations) == 1
        assert report.violations[0].detected_by == DetectionSource.STRUCTURAL
        assert report.recommendations == []
        assert report.semantic_analysis_skipped is False


class TestMeasurementInstrumentation:
    """Fase 10 (.cursor/specs/fase10.spec.md, secao 3.3/3.4) —
    `processing_duration_seconds` e `semantic_analysis_usage` em
    `_build_report()`."""

    @pytest.mark.asyncio
    async def test_full_path_records_duration_and_propagates_semantic_usage(self):
        entity = _raw_entity("urn:1", illuminanceLevel=0.5)
        usage = SemanticAnalysisUsage(backend=InferenceBackend.OLLAMA, compute_seconds=0.42)
        semantic_analyzer = _FakeSemanticAnalyzer(result=SemanticAnalysisResult(usage=usage))
        use_case, repo = _make_use_case(
            _FakeContextBroker([entity]),
            _FakeSchemaCatalog(),
            semantic_analyzer=semantic_analyzer,
            clock=_SteppingClock(_NOW, step_seconds=1.0),
        )

        run_id = await use_case.execute(_TENANT, EntityType("Streetlight"))
        run = await repo.get_by_id(run_id, _TENANT)

        report = run.reports[0]
        assert report.processing_duration_seconds == pytest.approx(1.0)
        assert report.semantic_analysis_usage is usage

    @pytest.mark.asyncio
    async def test_no_model_found_still_records_duration_without_semantic_usage(self):
        entity = _raw_entity("urn:1", entity_type="UnknownType")
        use_case, repo = _make_use_case(
            _FakeContextBroker([entity]),
            _FakeSchemaCatalog(no_model_for={"UnknownType"}),
            semantic_analyzer=_FakeSemanticAnalyzer(should_not_be_called=True),
            knowledge_retriever=_FakeKnowledgeRetriever(should_not_be_called=True),
            clock=_SteppingClock(_NOW, step_seconds=2.0),
        )

        run_id = await use_case.execute(_TENANT, EntityType("UnknownType"))
        run = await repo.get_by_id(run_id, _TENANT)

        report = run.reports[0]
        assert report.status == ConformanceStatus.NO_MODEL_FOUND
        assert report.processing_duration_seconds == pytest.approx(2.0)
        assert report.semantic_analysis_usage is None

    @pytest.mark.asyncio
    async def test_schema_unavailable_still_records_duration_without_semantic_usage(self):
        entity = _raw_entity("urn:1", illuminanceLevel=0.5)
        catalog = _FakeSchemaCatalog(unavailable_for={"Streetlight"})
        use_case, repo = _make_use_case(
            _FakeContextBroker([entity]),
            catalog,
            semantic_analyzer=_FakeSemanticAnalyzer(should_not_be_called=True),
            knowledge_retriever=_FakeKnowledgeRetriever(should_not_be_called=True),
            clock=_SteppingClock(_NOW, step_seconds=1.5),
        )

        run_id = await use_case.execute(_TENANT, EntityType("Streetlight"))
        run = await repo.get_by_id(run_id, _TENANT)

        report = run.reports[0]
        assert report.status == ConformanceStatus.SCHEMA_UNAVAILABLE
        assert report.processing_duration_seconds == pytest.approx(1.5)
        assert report.semantic_analysis_usage is None

    @pytest.mark.asyncio
    async def test_malformed_attribute_still_records_duration_without_semantic_usage(self):
        entity = {"id": "urn:bad", "type": "Streetlight", "illuminanceLevel": 0.5}  # sem envelope
        use_case, repo = _make_use_case(
            _FakeContextBroker([entity]),
            _FakeSchemaCatalog(),
            semantic_analyzer=_FakeSemanticAnalyzer(should_not_be_called=True),
            knowledge_retriever=_FakeKnowledgeRetriever(should_not_be_called=True),
            clock=_SteppingClock(_NOW, step_seconds=0.25),
        )

        run_id = await use_case.execute(_TENANT, EntityType("Streetlight"))
        run = await repo.get_by_id(run_id, _TENANT)

        report = run.reports[0]
        assert report.violations[0].rule == "malformed_attribute"
        assert report.processing_duration_seconds == pytest.approx(0.25)
        assert report.semantic_analysis_usage is None
