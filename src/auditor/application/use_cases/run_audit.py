"""RunAuditUseCase — orquestra Nivel 1 ponta a ponta. Ver
.cursor/specs/fase4.spec.md, secao 3, .cursor/specs/fase5.spec.md, secao 5,
e docs/plano_refatoracao_v3.md, Parte III, 2.2 (application/use_cases/run_audit.py).

Decisao de design (nao literal na spec, necessaria para reconciliar duas
exigencias dela): a spec pede (a) que `execute()` "rode ate o fim" nos casos
de teste — ou seja, bloqueante, devolve o run_id so' quando o run chega a um
status terminal — e (b) que `POST /audits` devolva `202` com o `run_id` "ja'
desde ja", sem esperar o processamento. As duas coexistem separando
`execute()` (usado pelo CLI, que quer o resultado final) em duas etapas
reutilizaveis: `create_run()` (so' cria o run, devolve o id imediatamente) +
`process_run()` (processa tudo, ate' status terminal). O CLI (Fase 4,
sem fila) continua chamando `execute()` sem nenhuma mudanca de
comportamento.

Fase 5 (fila e worker, secao 5 do spec): a API REST e o AuditWorker nao
usam mais `create_run()`/`process_run()` — usam `start()`/`process()`,
duas operacoes novas e deliberadamente distintas de `create_run()`/
`process_run()`:

- `start()` cria o run E publica o AuditJob na fila (O(1), nunca bloqueia
  a requisicao HTTP com o tamanho do lote).
- `process()` e' a versao usada pelo AuditWorker apos consumir um job da
  fila: ao contrario de `process_run()` (que CAPTURA falha de
  infraestrutura e marca o run PARTIAL/FAILED sozinho, pensado para uma
  execucao unica sem reentrega, como o CLI), `process()` deixa qualquer
  excecao de infraestrutura propagar de proposito — e' o que permite ao
  AuditWorker chamar nack() e deixar a PROPRIA FILA decidir reentrega ou
  DLQ (.cursor/specs/fase5.spec.md, secao 3.1). Reprocessar do zero a cada
  chamada e' seguro: append_report() e' idempotente por (run_id,
  entity_id) desde a Fase 3, e a validacao estrutural e' uma funcao pura
  (mesma entidade + mesmo schema sempre produz o mesmo resultado).
- `mark_failed()` e' chamado pelo AuditWorker quando um job excede o
  limite de tentativas e vai para a fila de mensagens mortas (DLQ) — o
  AuditRun correspondente nunca fica "pendente para sempre" sem explicacao
  visivel ao usuario (secao 3.1, ultimo caso de teste).

Resiliencia de `process_run()` (secao 3.2/3.3 da Fase 4): tres categorias
de resultado por entidade, bem distintas:
1. Resultado valido de auditoria (NO_MODEL_FOUND, SCHEMA_UNAVAILABLE, ou
   violacao de mapeamento/estrutural) — vira EntityReport, nunca aborta o
   run.
2. Falha ao obter QUALQUER entidade (ContextBrokerUnavailableError antes do
   loop) — run inteiro FAILED, nada foi processado.
3. Falha inesperada NO MEIO do loop (rede, banco, o que for, depois de
   algumas entidades ja' persistidas) — run PARTIAL, o que ja' foi
   processado fica persistido e consultavel, o loop para ali.

Fase 7 (Nivel 2 / SLM, .cursor/specs/fase7.spec.md, secao 4) — REVISADO pela
ADR-0014: `_build_report()` aciona `SemanticAnalyzerPort` SEMPRE que o Nivel
1 resolveu um schema e produziu `plain_values` validos, independente do
`ConformanceStatus` derivado (CONFORMANT incluido). Motivo da revisao: um
Smart Data Model tem ligacao semantica forte que nenhuma regra de JSON
Schema (tipo/obrigatoriedade/formato/faixa/enum) esgota — uma entidade pode
passar 100% no Nivel 1 e ainda estar semanticamente incoerente, e essa e'
justamente a categoria de erro que a regra antiga (SLM so' refina o que o
Nivel 1 ja reprovou) deixava fora de alcance. Continuam SEM acionar o Nivel
2, porque nao ha contexto coerente para montar um `SemanticAnalysisContext`:
NO_MODEL_FOUND, SCHEMA_UNAVAILABLE, e o caminho de `MalformedAttributeError`
(envelope NGSI-v2 invalido, antes de `to_plain_values()` sequer terminar).
`status` e' sempre RE-DERIVADO sobre a lista combinada de violacoes
estruturais + semanticas via `ConformanceStatus.derive()` — nunca herdado do
Nivel 1 sozinho, porque uma violacao ERROR encontrada so' pelo Nivel 2 pode
piorar CONFORMANT/PARTIAL para NON_CONFORMANT.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from uuid import UUID

from auditor.domain.entities.audit_job import AuditJob
from auditor.domain.entities.audit_run import AuditRun, RunStatus
from auditor.domain.entities.entity_report import EntityReport
from auditor.domain.entities.violation import (
    DetectionSource,
    Violation,
    ViolationSeverity,
)
from auditor.domain.errors import (
    ContextBrokerUnavailableError,
    MalformedAttributeError,
    SchemaUnavailableError,
)
from auditor.domain.ports.context_broker_port import ContextBrokerPort, RawEntity
from auditor.domain.ports.job_queue_port import JobQueuePort
from auditor.domain.ports.knowledge_retriever_port import KnowledgeRetrieverPort
from auditor.domain.ports.schema_catalog_port import SchemaCatalogPort
from auditor.domain.ports.semantic_analyzer_port import (
    SemanticAnalysisContext,
    SemanticAnalyzerPort,
)
from auditor.domain.ports.unit_of_work import UnitOfWork
from auditor.domain.services.structural_validator import StructuralValidator
from auditor.domain.value_objects.conformance_status import ConformanceStatus
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.context_broker.ngsi_v2_mapper import NgsiV2Mapper


def _semantic_query_from(violations: list[Violation], entity_type: EntityType) -> str:
    """Fase 7, secao 4, nota 3: a ponte entre uma Violation real e uma
    busca vetorial (Fase 6) e' decidida aqui, nao no KnowledgeRetrieverPort
    — que so' recebe texto livre.

    ADR-0014: uma entidade CONFORMANT chega aqui sem nenhuma violacao
    estrutural para descrever — uma query vazia nao ajudaria a busca
    vetorial do RAG, entao usamos uma query generica de verificacao
    semantica pelo tipo, para o Nivel 2 ainda receber chunks relevantes do
    corpus curado (convencoes/casos anotados) mesmo sem um erro estrutural
    como gatilho."""
    if not violations:
        return f"verificacao semantica geral de {entity_type.value}"
    return "; ".join(f"{v.rule} em {v.attribute_path}" for v in violations)


class RunAuditUseCase:
    def __init__(
        self,
        context_broker: ContextBrokerPort,
        schema_catalog: SchemaCatalogPort,
        validator: StructuralValidator,
        mapper: NgsiV2Mapper,
        uow: UnitOfWork,
        *,
        broker_url: str,
        clock: Callable[[], datetime] | None = None,
        job_queue: JobQueuePort | None = None,
        knowledge_retriever: KnowledgeRetrieverPort | None = None,
        semantic_analyzer: SemanticAnalyzerPort | None = None,
    ) -> None:
        self._context_broker = context_broker
        self._schema_catalog = schema_catalog
        self._validator = validator
        self._mapper = mapper
        self._uow = uow
        self._broker_url = broker_url
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        # Opcional de proposito (Fase 4 nao tinha fila nenhuma): so'
        # `start()` (Fase 5) precisa dele — `execute()`/`create_run()`/
        # `process_run()` (CLI) nunca tocam `self._job_queue`, entao os
        # testes/usos de Fase 4 que instanciam RunAuditUseCase sem fila
        # continuam funcionando sem alteracao nenhuma.
        self._job_queue = job_queue
        # Fase 7 (.cursor/specs/fase7.spec.md, secao 4), regra de
        # acionamento revisada pela ADR-0014: opcionais pelo mesmo motivo —
        # so' `_build_report()` os usa, e agora precisa deles sempre que o
        # Nivel 1 resolve um schema (nao mais so' em NON_CONFORMANT/
        # PARTIAL). Se `_build_report()` precisar deles e nenhum estiver
        # configurado, levanta RuntimeError explicito (mesmo padrao de
        # `start()` acima) em vez de pular o Nivel 2 em silencio — quem
        # monta o container (infrastructure/config/container.py) sempre
        # os fornece em producao.
        self._knowledge_retriever = knowledge_retriever
        self._semantic_analyzer = semantic_analyzer

    async def execute(
        self,
        tenant: Tenant,
        entity_type: EntityType | None = None,
        entity_id: str | None = None,
    ) -> UUID:
        """Cria o run e processa ate' o fim (bloqueante) — uso tipico: CLI,
        que quer imprimir o status final quando o comando termina."""
        run = await self.create_run(tenant, entity_type, entity_id)
        await self.process_run(run.id, tenant, entity_type, entity_id)
        return run.id

    async def create_run(
        self,
        tenant: Tenant,
        entity_type: EntityType | None = None,
        entity_id: str | None = None,
    ) -> AuditRun:
        """Cria o run em QUEUED e devolve imediatamente, sem processar
        nenhuma entidade — uso tipico: API REST, que precisa do run_id para
        responder 202 antes do processamento acabar."""
        run = AuditRun.create(
            tenant=tenant, entity_type=entity_type, broker_url=self._broker_url
        )
        async with self._uow as uow:
            await uow.audits.create_run(run)
        return run

    async def process_run(
        self,
        run_id: UUID,
        tenant: Tenant,
        entity_type: EntityType | None = None,
        entity_id: str | None = None,
    ) -> None:
        """Processa um run ja' criado ate' um status terminal
        (COMPLETED/FAILED/PARTIAL) numa unica passada, sem fila — uso
        tipico: CLI (via `execute()`), que roda uma vez e reporta o
        resultado final na hora, sem reentrega automatica. Ver `process()`
        para a versao usada pelo AuditWorker (Fase 5), que se comporta
        diferente de proposito."""
        try:
            raw_entities = await self._context_broker.fetch_entities(
                tenant, entity_type, entity_id
            )
        except ContextBrokerUnavailableError:
            async with self._uow as uow:
                await uow.audits.update_run_status(
                    run_id, tenant, RunStatus.FAILED, finished_at=self._clock()
                )
            return

        partial = False
        for raw_entity in raw_entities:
            try:
                report = await self._build_report(raw_entity)
                async with self._uow as uow:
                    await uow.audits.append_report(run_id, tenant, report)
            except Exception:
                # Categoria 3 do docstring do modulo: falha inesperada no
                # meio do lote. O que ja' foi persistido nas iteracoes
                # anteriores (cada append_report e' sua propria transacao,
                # Fase 3) permanece — so' paramos de processar o resto.
                partial = True
                break

        final_status = RunStatus.PARTIAL if partial else RunStatus.COMPLETED
        async with self._uow as uow:
            await uow.audits.update_run_status(
                run_id, tenant, final_status, finished_at=self._clock()
            )

    async def start(
        self,
        tenant: Tenant,
        entity_type: EntityType | None = None,
        entity_id: str | None = None,
    ) -> UUID:
        """Fase 5 (.cursor/specs/fase5.spec.md, secao 5): cria o run e
        publica um AuditJob na fila — nao processa nada aqui, e' O(1)
        independente do numero de entidades a auditar. Uso tipico:
        `POST /audits`, que devolve 202 assim que o job existe; quem
        processa de fato e' o AuditWorker, consumindo da fila
        (`process()`)."""
        if self._job_queue is None:
            raise RuntimeError(
                "RunAuditUseCase.start() requer job_queue configurado — ver "
                "infrastructure/config/container.py, get_run_audit_use_case()."
            )
        run = await self.create_run(tenant, entity_type, entity_id)
        job = AuditJob(
            run_id=run.id,
            tenant=tenant,
            entity_type=entity_type,
            entity_id=entity_id,
            enqueued_at=self._clock(),
        )
        await self._job_queue.enqueue(job)
        return run.id

    async def process(
        self,
        run_id: UUID,
        tenant: Tenant,
        entity_type: EntityType | None = None,
        entity_id: str | None = None,
    ) -> None:
        """Fase 5, secao 5: processa um run ja' criado — chamado pelo
        AuditWorker apos consumir um AuditJob da fila (`job.run_id`,
        `job.tenant`, `job.entity_type`, `job.entity_id` viram os
        argumentos aqui, sem round-trip ao banco so' para saber o tenant).

        Ao contrario de `process_run()`, NAO CAPTURA falha de
        infraestrutura (ContextBrokerUnavailableError, ou qualquer excecao
        inesperada no meio do lote): deixa propagar de proposito, para que
        o AuditWorker chame `nack()` e a propria fila decida reentrega/DLQ
        (secao 3.1). Reprocessa TODAS as entidades do zero a cada chamada
        — nunca so' as que faltaram — porque e' exatamente isso que torna
        reentrega segura: `append_report()` e' idempotente por (run_id,
        entity_id) desde a Fase 3, entao reprocessar uma entidade ja'
        persistida so' a substitui pelo mesmo resultado (validacao
        estrutural e' uma funcao pura), nunca duplica."""
        async with self._uow as uow:
            await uow.audits.update_run_status(run_id, tenant, RunStatus.RUNNING)

        raw_entities = await self._context_broker.fetch_entities(tenant, entity_type, entity_id)

        async with self._uow as uow:
            await uow.audits.set_total_entities(run_id, tenant, len(raw_entities))

        for raw_entity in raw_entities:
            report = await self._build_report(raw_entity)
            async with self._uow as uow:
                await uow.audits.append_report(run_id, tenant, report)

        async with self._uow as uow:
            await uow.audits.update_run_status(
                run_id, tenant, RunStatus.COMPLETED, finished_at=self._clock()
            )

    async def mark_failed(self, run_id: UUID, tenant: Tenant, reason: str) -> None:
        """Fase 5, secao 3.1 (ultimo caso de teste): usado pelo AuditWorker
        quando um job excede o limite de tentativas configurado na fila e
        vai para a DLQ — o AuditRun correspondente e' marcado FAILED com o
        motivo, nunca fica "pendente para sempre" sem explicacao visivel."""
        async with self._uow as uow:
            await uow.audits.update_run_status(
                run_id, tenant, RunStatus.FAILED, finished_at=self._clock(), failure_reason=reason
            )

    async def _build_report(self, raw_entity: RawEntity) -> EntityReport:
        """Produz o EntityReport de uma entidade — nunca levanta
        MalformedAttributeError/SchemaUnavailableError para fora: sao
        resultados validos de auditoria (categoria 1), viram status
        especificos, nao interrompem o lote."""
        # Fase 10 (.cursor/specs/fase10.spec.md, secao 2/3.3): duracao de
        # processamento POR ENTIDADE, granularidade que o run como um todo
        # (AuditRun.started_at/finished_at) nao da'. Reaproveita `self._clock`
        # (ja' injetavel pelos testes existentes) em vez de um relogio novo —
        # um clock de teste fixo (`lambda: _NOW`) produz duracao 0.0,
        # deterministico, sem quebrar nenhum teste ja existente que nao se
        # importa com este campo.
        started_at = self._clock()

        entity_id = raw_entity["id"]
        entity_type = EntityType(raw_entity["type"])

        data_model = await self._schema_catalog.resolve_data_model(entity_type)
        if data_model is None:
            return EntityReport(
                entity_id=entity_id,
                entity_type=entity_type,
                data_model=None,
                status=ConformanceStatus.NO_MODEL_FOUND,
                violations=[],
                processing_duration_seconds=(self._clock() - started_at).total_seconds(),
            )

        try:
            resolved_schema = await self._schema_catalog.fetch_schema(data_model)
        except SchemaUnavailableError:
            return EntityReport(
                entity_id=entity_id,
                entity_type=entity_type,
                data_model=data_model,
                status=ConformanceStatus.SCHEMA_UNAVAILABLE,
                violations=[],
                processing_duration_seconds=(self._clock() - started_at).total_seconds(),
            )

        try:
            plain_values = self._mapper.to_plain_values(raw_entity)
        except MalformedAttributeError as exc:
            violation = Violation(
                attribute_path=exc.attribute_name,
                severity=ViolationSeverity.ERROR,
                rule="malformed_attribute",
                expected="envelope NGSI-v2 ({'type':..., 'value':...})",
                found=None,
                message=str(exc),
                detected_by=DetectionSource.STRUCTURAL,
            )
            return EntityReport(
                entity_id=entity_id,
                entity_type=entity_type,
                data_model=data_model,
                status=ConformanceStatus.derive([violation], model_found=True),
                violations=[violation],
                schema_origin=resolved_schema.origin,
                processing_duration_seconds=(self._clock() - started_at).total_seconds(),
            )

        structural_violations = self._validator.validate(plain_values, resolved_schema.content)

        # ADR-0014: o Nivel 2 roda sempre a partir daqui — schema resolvido
        # e plain_values validos sao o unico pre-requisito, nao mais o
        # status do Nivel 1. Uma entidade CONFORMANT no Nivel 1 chega aqui
        # e e' examinada semanticamente do mesmo jeito.
        if self._knowledge_retriever is None or self._semantic_analyzer is None:
            raise RuntimeError(
                "RunAuditUseCase._build_report() precisa de knowledge_retriever "
                "e semantic_analyzer configurados sempre que o Nivel 1 resolve "
                "um schema (ADR-0014: o Nivel 2 roda em toda entidade, nao so' "
                "nas reprovadas) — ver infrastructure/config/container.py, "
                "get_run_audit_use_case()."
            )

        chunks = await self._knowledge_retriever.retrieve(
            _semantic_query_from(structural_violations, entity_type)
        )
        semantic_result = await self._semantic_analyzer.analyze(
            SemanticAnalysisContext(
                entity_id=entity_id,
                entity_type=entity_type,
                plain_values=plain_values,
                schema=resolved_schema.content,
                structural_violations=tuple(structural_violations),
                knowledge_chunks=tuple(chunks),
            )
        )

        all_violations = [*structural_violations, *semantic_result.violations]
        final_status = ConformanceStatus.derive(all_violations, model_found=True)
        return EntityReport(
            entity_id=entity_id,
            entity_type=entity_type,
            data_model=data_model,
            status=final_status,
            violations=all_violations,
            recommendations=list(semantic_result.recommendations),
            schema_origin=resolved_schema.origin,
            semantic_analysis_skipped=False,
            processing_duration_seconds=(self._clock() - started_at).total_seconds(),
            semantic_analysis_usage=semantic_result.usage,
        )
