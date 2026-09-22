"""SyncCatalogUseCase — orquestra CatalogIndex.sync() (Fase 2) +
CatalogSyncStatusRepository.record() (Fase 8, secao 7).

Administrativo por design: nenhum endpoint HTTP dispara isto (mesmo
padrao ja' aceito para a sincronizacao do catalogo na Fase 2 e do corpus
RAG na Fase 6, .cursor/specs/fase6.spec.md secao 8) — a Fase 8 so exige
que o RESULTADO de uma sincronizacao fique visivel via `GET /catalog`.

O gatilho administrativo e' o comando `audit catalog sync`
(interfaces/cli/main.py) -- adicionado depois da Fase 8 ao constatar que,
sem ele, nao havia NENHUM jeito de popular o que `GET /catalog` mostra
fora dos testes unitarios (a tela Catalog do frontend sempre mostrava
"nunca sincronizado").
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Callable

from auditor.infrastructure.schema_catalog.catalog_index import CatalogIndex, SyncResult
from auditor.infrastructure.schema_catalog.catalog_sync_status_repository import (
    CatalogSyncStatusRepository,
)


class SyncCatalogUseCase:
    def __init__(
        self,
        catalog_index: CatalogIndex,
        status_repository: CatalogSyncStatusRepository,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._catalog_index = catalog_index
        self._status_repository = status_repository
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def execute(self) -> SyncResult:
        # CatalogIndex.sync() e' sincrono (Fase 2: pysmartdatamodels nao
        # expoe uma API assincrona) E bloqueante de rede — update_data()
        # busca o catalogo oficial do GitHub, "vai demorar um pouco" pela
        # propria documentacao da biblioteca (pode levar minutos, sem
        # timeout interno).
        #
        # Bug real encontrado ao investigar por que `uvicorn` nunca
        # terminava de subir (travava para sempre em "Waiting for
        # application startup.", sem nenhuma porta chegando a abrir):
        # chamar isto direto (sem to_thread) era seguro na Fase 8, quando
        # SO' o CLI `audit catalog sync` disparava isto — um processo de
        # vida curta dedicado exclusivamente a essa tarefa, sem mais
        # ninguem compartilhando o event loop. Deixou de ser seguro quando
        # CatalogSyncScheduler (follow-up pos-Fase 8,
        # interfaces/worker/catalog_sync_scheduler.py) passou a chamar
        # isto automaticamente, logo na primeira iteracao do seu
        # `run_forever()`, dentro do MESMO processo/event loop da API REST
        # (interfaces/rest/app.py::_make_lifespan) — uma chamada sincrona
        # bloqueante ali trava o loop INTEIRO enquanto dura (nenhuma
        # requisicao HTTP, nem o proprio bind do socket de escuta,
        # progride), o que por fora parece a API inteira travada/sem
        # responder. `asyncio.to_thread` roda a chamada bloqueante numa
        # thread separada, liberando o event loop para tudo o mais
        # enquanto o sync acontece — mesmo padrao ja usado em
        # infrastructure/rag/embedder.py para SentenceTransformer.encode().
        result = await asyncio.to_thread(self._catalog_index.sync)
        await self._status_repository.record(result, attempted_at=self._clock())
        return result
