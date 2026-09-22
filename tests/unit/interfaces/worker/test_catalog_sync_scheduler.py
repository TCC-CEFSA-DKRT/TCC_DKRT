"""CatalogSyncScheduler — sincroniza o catalogo de Smart Data Models
sozinho, em background, sem depender de alguem rodar `audit catalog sync`
manualmente. Ver interfaces/worker/catalog_sync_scheduler.py.

Os testes usam um intervalo minusculo (segundos reais, nao um relogio
fake) para observar varios ciclos rapidamente e depois cancelam a task —
mesmo estilo de teste de loop em background usado nesta base (ver
AuditWorker: consome ate' ser cancelado).
"""

from __future__ import annotations

import asyncio

import pytest

from auditor.infrastructure.schema_catalog.catalog_index import SyncResult
from auditor.interfaces.worker.catalog_sync_scheduler import CatalogSyncScheduler

_TINY_INTERVAL = 0.01


class _FakeSyncUseCase:
    def __init__(self, results: list[SyncResult] | None = None):
        # Se `results` for None, todo execute() devolve sucesso — usado
        # nos testes que so' querem contar chamadas, nao inspecionar
        # resultados especificos.
        self._results = results
        self.call_count = 0

    async def execute(self) -> SyncResult:
        self.call_count += 1
        if self._results is not None:
            return self._results[min(self.call_count, len(self._results)) - 1]
        return SyncResult(success=True, models_count=7, reason=None)


class _RaisingSyncUseCase:
    def __init__(self):
        self.call_count = 0

    async def execute(self) -> SyncResult:
        self.call_count += 1
        raise RuntimeError("catalogo upstream indisponivel")


async def _run_briefly_then_cancel(scheduler: CatalogSyncScheduler, seconds: float) -> None:
    task = asyncio.create_task(scheduler.run_forever())
    await asyncio.sleep(seconds)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


class TestRunForever:
    @pytest.mark.asyncio
    async def test_syncs_immediately_on_start_without_waiting_a_full_interval(self):
        use_case = _FakeSyncUseCase()
        scheduler = CatalogSyncScheduler(sync_use_case=use_case, interval_seconds=999)

        task = asyncio.create_task(scheduler.run_forever())
        await asyncio.sleep(0)  # cede o loop de eventos o suficiente para o 1o ciclo comecar
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert use_case.call_count >= 1

    @pytest.mark.asyncio
    async def test_syncs_again_after_each_interval_elapses(self):
        use_case = _FakeSyncUseCase()
        scheduler = CatalogSyncScheduler(sync_use_case=use_case, interval_seconds=_TINY_INTERVAL)

        await _run_briefly_then_cancel(scheduler, seconds=_TINY_INTERVAL * 5)

        # Com um intervalo minusculo e ~5 intervalos de espera, espera-se
        # mais de uma sincronizacao — o ponto do teste e' "periodico", nao
        # um numero exato de ciclos (evita flakiness por timing).
        assert use_case.call_count >= 2

    @pytest.mark.asyncio
    async def test_a_failed_sync_result_does_not_stop_the_loop(self):
        use_case = _FakeSyncUseCase(
            results=[
                SyncResult(success=False, models_count=None, reason="timeout"),
                SyncResult(success=True, models_count=3, reason=None),
            ]
        )
        scheduler = CatalogSyncScheduler(sync_use_case=use_case, interval_seconds=_TINY_INTERVAL)

        await _run_briefly_then_cancel(scheduler, seconds=_TINY_INTERVAL * 5)

        assert use_case.call_count >= 2

    @pytest.mark.asyncio
    async def test_an_unexpected_exception_does_not_stop_the_loop(self):
        use_case = _RaisingSyncUseCase()
        scheduler = CatalogSyncScheduler(sync_use_case=use_case, interval_seconds=_TINY_INTERVAL)

        # Nao deve propagar: uma excecao fora de SyncResult (ex.: falha ao
        # gravar o status) e' logada e o loop continua no proximo ciclo.
        await _run_briefly_then_cancel(scheduler, seconds=_TINY_INTERVAL * 5)

        assert use_case.call_count >= 2
