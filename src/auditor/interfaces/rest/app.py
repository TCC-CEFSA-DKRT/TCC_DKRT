"""FastAPI app factory. Ver .cursor/specs/fase4.spec.md, secao 4,
.cursor/specs/fase5.spec.md, secao 3, e docs/plano_refatoracao_v3.md,
Parte III, 2.2 (interfaces/rest/app.py).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from auditor.domain.errors import TenantBrokerNotConfiguredError
from auditor.infrastructure.config.container import (
    get_job_queue,
    get_run_audit_use_case,
    get_settings,
    get_sync_catalog_use_case,
)
from auditor.interfaces.rest.routers import (
    audits,
    auth,
    catalog,
    config,
    entity_types,
    health,
    session,
)
from auditor.interfaces.worker.audit_worker import AuditWorker
from auditor.interfaces.worker.catalog_sync_scheduler import CatalogSyncScheduler


def _make_lifespan(*, start_background_workers: bool):
    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Fase 5 (.cursor/specs/fase5.spec.md, secao 3): o AuditWorker roda
        # como uma task em background, no MESMO processo da API, consumindo
        # da mesma instancia de LocalJobQueue que o router usa para
        # enfileirar em POST /audits — get_job_queue() e' @lru_cache
        # justamente para garantir isso. E' necessario em desenvolvimento
        # porque LocalJobQueue e' 100% em memoria (sem broker externo); no
        # EC2 de producao (SqsJobQueue) o worker roda num processo separado,
        # mas esta task em background continua existindo tambem ali (mais
        # um consumidor da mesma fila, redundante mas inofensivo — SQS
        # entrega uma vez por consumidor disponivel).
        #
        # ADR-0017: no Lambda de producao isso PRECISA ficar desligado
        # (start_background_workers=False, ver aws_lambda/api_handler.py).
        # Uma task asyncio de longa duracao sobrevivendo entre invocacoes
        # de um Lambda e' um anti-padrao — o ambiente de execucao pode
        # congelar/retomar o processo entre chamadas, e o Worker/scheduler
        # ja' rodam como Lambdas proprios, acionados por evento (SQS
        # event source mapping / EventBridge), nao por polling em processo.
        if not start_background_workers:
            yield
            return

        worker = AuditWorker(queue=get_job_queue(), run_audit=get_run_audit_use_case())
        worker_task = asyncio.create_task(worker.run_forever())

        # Segunda task em background: mantem o catalogo de Smart Data Models
        # sincronizado sozinho enquanto a API estiver de pe (sincroniza no
        # startup + a cada Settings.catalog_sync_interval_seconds), sem
        # exigir que alguem rode `audit catalog sync` manualmente toda vez
        # que o catalogo upstream mudar -- ver CatalogSyncScheduler para o
        # raciocinio completo.
        scheduler = CatalogSyncScheduler(
            sync_use_case=get_sync_catalog_use_case(),
            interval_seconds=get_settings().catalog_sync_interval_seconds,
        )
        scheduler_task = asyncio.create_task(scheduler.run_forever())

        try:
            yield
        finally:
            worker_task.cancel()
            scheduler_task.cancel()
            for task in (worker_task, scheduler_task):
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    return _lifespan


async def _tenant_account_gone(request: Request, exc: TenantBrokerNotConfiguredError) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"detail": "Conta nao encontrada; faca login novamente."},
        headers={"WWW-Authenticate": "Bearer"},
    )


def create_app(*, start_background_workers: bool = True) -> FastAPI:
    app = FastAPI(
        title="FIWARE Conformance Auditor",
        lifespan=_make_lifespan(start_background_workers=start_background_workers),
    )
    # Fase 8 (.cursor/specs/fase8.spec.md, secao 9): o frontend Angular
    # (ng serve, localhost:4200 por padrao) chama esta API a partir de uma
    # origem diferente -- sem CORS liberado, o navegador bloqueia a
    # resposta antes mesmo dela chegar ao codigo do frontend. Headers
    # Fiware-Service/Fiware-ServicePath (dependencies.get_tenant) precisam
    # estar em allow_headers, senao o preflight OPTIONS os rejeita.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(TenantBrokerNotConfiguredError, _tenant_account_gone)
    app.include_router(audits.router)
    app.include_router(catalog.router)
    app.include_router(entity_types.router)
    app.include_router(health.router)
    app.include_router(session.router)
    if get_settings().deployment_mode == "saas":
        app.include_router(auth.router)
    else:
        app.include_router(config.router)
    return app


app = create_app()
