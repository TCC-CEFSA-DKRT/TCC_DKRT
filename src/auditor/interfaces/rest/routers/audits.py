"""POST /audits, GET /audits, GET /audits/summary-over-time,
POST /audits/interpret, GET /audits/{run_id}, GET /audits/{run_id}/progress
e GET /audits/{run_id}/stream. Ver .cursor/specs/fase4.spec.md, secao
4.1/4.3, .cursor/specs/fase5.spec.md, secao 5 (POST /audits chama start(),
nao mais execute()/create_run()+BackgroundTasks) e secao 4 (progress/
stream), e .cursor/specs/fase8.spec.md, secao 0 (os tres endpoints novos
desta fase, que a tela "Audit Runs"/"Dashboard"/"Natural Language" do
frontend consomem).

ORDEM DE REGISTRO IMPORTA: `/audits/summary-over-time` e `/audits/interpret`
sao registrados ANTES de `/audits/{run_id}` de proposito — Starlette casa
rotas na ordem em que sao registradas, e `{run_id}` (sem conversor
explicito de path) casaria com o literal "summary-over-time"/"interpret"
antes de FastAPI sequer tentar validar como UUID, devolvendo 422 em vez de
rotear para o endpoint certo.
"""

from __future__ import annotations

import asyncio
import json
from uuid import UUID

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from auditor.application.use_cases.interpret_audit_command import InterpretAuditCommandUseCase
from auditor.application.use_cases.run_audit import RunAuditUseCase
from auditor.domain.entities.audit_run import RunStatus
from auditor.domain.ports.audit_repository_port import RunFilters
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.config.container import (
    get_interpret_audit_command_use_case,
    get_run_audit_use_case,
    get_unit_of_work,
)
from auditor.infrastructure.persistence.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
from auditor.interfaces.rest.dependencies import get_tenant
from auditor.interfaces.rest.schemas import (
    AuditCreateRequest,
    AuditCreateResponse,
    AuditProgressResponse,
    AuditRunResponse,
    AuditRunSummaryResponse,
    InterpretAuditRequest,
    InterpretAuditResponse,
    PageResponse,
)

router = APIRouter(prefix="/audits", tags=["audits"])

_TERMINAL_STATUSES = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.PARTIAL}
_STREAM_POLL_INTERVAL_SECONDS = 1.0


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=AuditCreateResponse)
async def create_audit(
    body: AuditCreateRequest,
    tenant: Tenant = Depends(get_tenant),
    use_case: RunAuditUseCase = Depends(get_run_audit_use_case),
) -> AuditCreateResponse:
    entity_type = EntityType(body.entity_type) if body.entity_type else None

    # Fase 5: start() cria o run E publica o AuditJob na fila, sem
    # processar nada aqui — O(1) independente do numero de entidades, e'
    # o que garante que a resposta nao trava numa auditoria grande (quem
    # processa de fato e' o AuditWorker rodando em background, ver
    # interfaces/rest/app.py). run.status e' sempre QUEUED logo apos
    # AuditRun.create() — nao precisa de outra consulta ao banco so' para
    # confirmar isso.
    run_id = await use_case.start(tenant, entity_type, body.entity_id)
    return AuditCreateResponse(run_id=run_id, status=RunStatus.QUEUED.value)


@router.get("", response_model=PageResponse[AuditRunSummaryResponse])
async def list_audits(
    tenant: Tenant = Depends(get_tenant),
    entity_type: str | None = None,
    # alias="status" e' obrigatorio aqui: sem ele, FastAPI usaria o nome
    # literal do parametro Python ("status_") como o nome da query string
    # (o "_" evita colidir com o modulo fastapi.status importado acima) --
    # descoberto por um teste real (test_status_filter_is_passed_to_the_
    # repository_as_run_filters) falhando com RunFilters.status=None em vez
    # do valor esperado, porque "?status=failed" nunca era lido sem o alias.
    status_: RunStatus | None = Query(default=None, alias="status"),
    started_after: datetime | None = None,
    started_before: datetime | None = None,
    page: int = 1,
    page_size: int = 20,
    uow: SqlAlchemyUnitOfWork = Depends(get_unit_of_work),
) -> PageResponse[AuditRunSummaryResponse]:
    """Fase 8, secao 0.1 — tela "Audit Runs". So' a borda HTTP que faltava:
    reaproveita `AuditRepositoryPort.list_runs`/`RunFilters`/`Page` (Fase
    3), sem logica nova. `status_` (com underscore) porque `status` colide
    com o modulo `fastapi.status` ja' importado neste arquivo — o nome do
    parametro de QUERY continua "status" via `Query(alias="status")`
    (FastAPI NAO usa o nome do argumento Python como alias por padrao;
    sem o alias explicito a query string precisaria ser "?status_=...",
    o que quebraria o contrato da secao 0.1 do spec)."""
    filters = RunFilters(
        entity_type=EntityType(entity_type) if entity_type else None,
        status=status_,
        started_after=started_after,
        started_before=started_before,
        page=page,
        page_size=page_size,
    )
    async with uow:
        result = await uow.audits.list_runs(tenant, filters)

    items = [AuditRunSummaryResponse.from_domain(view) for view in result.items]
    return PageResponse.from_domain(result, items)


@router.get("/summary-over-time", response_model=list[AuditRunSummaryResponse])
async def get_summary_over_time(
    entity_type: str,
    tenant: Tenant = Depends(get_tenant),
    uow: SqlAlchemyUnitOfWork = Depends(get_unit_of_work),
) -> list[AuditRunSummaryResponse]:
    """Fase 8, secao 0.2 — dados do Dashboard (evolucao de conformidade no
    tempo). `entity_type` e' obrigatorio porque a agregacao e' sempre por
    tipo (Fase 8, secao 2) — nao existe uma visao "todos os tipos juntos"
    aqui, o dashboard decide quais tipos consultar."""
    async with uow:
        views = await uow.audits.list_run_summaries_over_time(tenant, EntityType(entity_type))
    return [AuditRunSummaryResponse.from_domain(view) for view in views]


@router.post("/interpret", response_model=InterpretAuditResponse)
async def interpret_audit_command(
    body: InterpretAuditRequest,
    tenant: Tenant = Depends(get_tenant),
    use_case: InterpretAuditCommandUseCase = Depends(get_interpret_audit_command_use_case),
) -> InterpretAuditResponse:
    """Fase 8, secao 0.3 — tela "Natural Language". NUNCA dispara uma
    auditoria: so' traduz o comando para os parametros que a tela mostra
    para confirmacao humana antes de um POST /audits separado (secao 6) —
    ver InterpretAuditCommandUseCase, que nunca chama RunAuditUseCase."""
    interpretation = await use_case.execute(tenant, body.command_text)
    return InterpretAuditResponse.from_domain(interpretation)


@router.get("/{run_id}", response_model=AuditRunResponse)
async def get_audit(
    run_id: UUID,
    tenant: Tenant = Depends(get_tenant),
    uow: SqlAlchemyUnitOfWork = Depends(get_unit_of_work),
) -> AuditRunResponse:
    async with uow:
        run = await uow.audits.get_by_id(run_id, tenant)

    if run is None:
        # Run existe mas e' de outro tenant, OU nao existe de fato — os dois
        # casos respondem 404 identicamente (nunca 403, que confirmaria a
        # existencia do recurso para quem nao deveria nem saber disso; Fase
        # 3, isolamento de tenant, agora replicado na borda HTTP).
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit run not found")

    return AuditRunResponse.from_domain(run)


@router.get("/{run_id}/progress", response_model=AuditProgressResponse)
async def get_audit_progress(
    run_id: UUID,
    tenant: Tenant = Depends(get_tenant),
    uow: SqlAlchemyUnitOfWork = Depends(get_unit_of_work),
) -> AuditProgressResponse:
    """Fase 5, secao 4.1/4.2. `processed` vem de um COUNT direto no banco
    (AuditRepositoryPort.count_reports), nunca de um valor em memoria do
    worker — multiplos consumidores da API precisam ver o mesmo progresso,
    entao a fonte de verdade e' o banco. `total` fica `None` ate' o worker
    terminar de consultar o Orion (nunca 0 inventado)."""
    async with uow:
        run = await uow.audits.get_by_id(run_id, tenant)
        if run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit run not found")
        processed = await uow.audits.count_reports(run_id, tenant)

    return AuditProgressResponse(
        status=run.status.value,
        processed=processed,
        total=run.total_entities_discovered,
    )


@router.get("/{run_id}/stream")
async def stream_audit_progress(
    run_id: UUID,
    tenant: Tenant = Depends(get_tenant),
    uow: SqlAlchemyUnitOfWork = Depends(get_unit_of_work),
) -> StreamingResponse:
    """Fase 5, secao 4.3 (SSE, opcional/escopo basico — spec explicito:
    "otimizacao de frequencia de eventos fica para refinamento posterior,
    nao bloqueia o criterio de pronto"). Implementacao por polling
    periodico no banco ate' um status terminal, em vez de notificacao
    push real — simples e correta, suficiente para o escopo desta fase."""

    async def event_source():
        while True:
            async with uow:
                run = await uow.audits.get_by_id(run_id, tenant)
                if run is None:
                    yield 'event: error\ndata: {"detail": "Audit run not found"}\n\n'
                    return
                processed = await uow.audits.count_reports(run_id, tenant)

            payload = json.dumps(
                {
                    "status": run.status.value,
                    "processed": processed,
                    "total": run.total_entities_discovered,
                }
            )
            yield f"data: {payload}\n\n"

            if run.status in _TERMINAL_STATUSES:
                return
            await asyncio.sleep(_STREAM_POLL_INTERVAL_SECONDS)

    return StreamingResponse(event_source(), media_type="text/event-stream")
