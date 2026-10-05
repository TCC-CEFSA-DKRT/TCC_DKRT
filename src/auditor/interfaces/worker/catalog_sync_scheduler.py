"""CatalogSyncScheduler — roda SyncCatalogUseCase periodicamente em
background, no mesmo processo da API (mesmo padrao do AuditWorker, ver
interfaces/worker/audit_worker.py e a fiacao em interfaces/rest/app.py).

Resolve um gap real encontrado apos a Fase 8: `audit catalog sync`
(interfaces/cli/main.py) e' o unico jeito de popular o que `GET /catalog`
mostra, mas exigir que alguem rode esse comando manualmente toda vez que o
catalogo upstream de Smart Data Models mudar nao e' sustentavel. Este
scheduler sincroniza uma vez no startup da API (para nunca ficar "nunca
sincronizado" mesmo antes do primeiro intervalo completar) e depois a cada
`interval_seconds` (Settings.catalog_sync_interval_seconds, default 24h --
o catalogo upstream nao muda com frequencia maior que isso na pratica)
enquanto o processo da API estiver de pe. Sem cron/scheduler externo: para
o escopo deste protótipo, manter isso dentro do próprio processo evita
infraestrutura operacional adicional (mesmo raciocinio do ADR-0013 sobre
não adicionar complexidade além do necessário).

Uma falha de sincronizacao (rede fora do ar, catalogo upstream
indisponivel) nunca derruba o loop -- o proximo ciclo tenta de novo, e
CatalogSyncStatusRepository ja' preserva o ultimo sucesso quando um
SyncResult(success=False) e' registrado (Fase 8, secao 7).
"""

from __future__ import annotations

import asyncio
import logging

from auditor.application.use_cases.sync_catalog import SyncCatalogUseCase

logger = logging.getLogger(__name__)


class CatalogSyncScheduler:
    def __init__(self, sync_use_case: SyncCatalogUseCase, interval_seconds: float) -> None:
        self._sync_use_case = sync_use_case
        self._interval_seconds = interval_seconds

    async def run_forever(self) -> None:
        while True:
            await self._sync_once()
            await asyncio.sleep(self._interval_seconds)

    async def _sync_once(self) -> None:
        try:
            result = await self._sync_use_case.execute()
        except Exception:
            # Erro fora do que SyncCatalogUseCase/SyncResult ja' modelam
            # (ex.: falha ao gravar o status no Postgres) -- nunca deixa o
            # loop morrer, so' loga e tenta de novo no proximo ciclo.
            logger.exception(
                "Falha inesperada ao sincronizar o catalogo — tentando de novo no proximo ciclo."
            )
            return

        if result.success:
            logger.info("Catalogo sincronizado: %s modelos.", result.models_count)
        else:
            logger.warning("Falha ao sincronizar catalogo: %s", result.reason)
