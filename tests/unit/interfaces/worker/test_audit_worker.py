"""Fase 5 — AuditWorker. Ver .cursor/specs/fase5.spec.md, secao 3.1."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from auditor.domain.entities.audit_job import AuditJob
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.queue.local_job_queue import LocalJobQueue
from auditor.interfaces.worker.audit_worker import MAX_RETRIES_EXCEEDED_REASON, AuditWorker

_TENANT = Tenant(fiware_service="openiot", fiware_service_path="/")
_NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _job() -> AuditJob:
    return AuditJob(
        run_id=uuid4(),
        tenant=_TENANT,
        entity_type=EntityType("Streetlight"),
        entity_id=None,
        enqueued_at=_NOW,
    )


async def _wait_until(predicate, timeout: float = 2.0, interval: float = 0.01) -> None:
    async def _poll():
        while not predicate():
            await asyncio.sleep(interval)

    await asyncio.wait_for(_poll(), timeout=timeout)


async def _cancel(*tasks: asyncio.Task) -> None:
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


class _FakeHandle:
    def __init__(self, job: AuditJob):
        self.job = job
        self.acked = False
        self.nacked = False

    async def ack(self) -> None:
        self.acked = True

    async def nack(self) -> None:
        self.nacked = True


class _FakeRunAudit:
    """Registra chamadas a process()/mark_failed(); pode ser configurado
    para falhar nas N primeiras chamadas a process() (simula falha de
    infraestrutura seguida de reentrega bem-sucedida)."""

    def __init__(self, fail_times: int = 0):
        self.process_calls: list[tuple] = []
        self.mark_failed_calls: list[tuple] = []
        self._fail_times = fail_times

    async def process(self, run_id, tenant, entity_type=None, entity_id=None) -> None:
        self.process_calls.append((run_id, tenant, entity_type, entity_id))
        if len(self.process_calls) <= self._fail_times:
            raise RuntimeError("falha simulada de infraestrutura")

    async def mark_failed(self, run_id, tenant, reason) -> None:
        self.mark_failed_calls.append((run_id, tenant, reason))


class TestProcessOne:
    """Fase 5, secao 3.1, primeiro e segundo casos de teste — sem fila
    real, so' o handle e o resultado de process()."""

    @pytest.mark.asyncio
    async def test_acks_on_successful_processing_even_with_unfavorable_conformance_result(self):
        # O worker nunca inspeciona o CONTEUDO do resultado (NON_CONFORMANT
        # etc.) — so' se process() levantou excecao ou nao. Um resultado de
        # auditoria desfavoravel NAO E' uma falha de processamento.
        job = _job()
        handle = _FakeHandle(job)
        run_audit = _FakeRunAudit(fail_times=0)
        worker = AuditWorker(queue=object(), run_audit=run_audit)

        await worker._process_one(handle)

        assert handle.acked is True
        assert handle.nacked is False
        assert run_audit.process_calls == [(job.run_id, job.tenant, job.entity_type, job.entity_id)]

    @pytest.mark.asyncio
    async def test_nacks_on_infrastructure_failure_during_processing(self):
        job = _job()
        handle = _FakeHandle(job)
        run_audit = _FakeRunAudit(fail_times=1)
        worker = AuditWorker(queue=object(), run_audit=run_audit)

        await worker._process_one(handle)

        assert handle.acked is False
        assert handle.nacked is True


class TestRedeliveryIntegration:
    """Fase 5, secao 3.1, terceiro caso de teste (reprocessamento) — aqui
    integrado com uma LocalJobQueue real para provar que o worker de fato
    reage a' reentrega da fila, nao so' que process()/handle se comportam
    isoladamente."""

    @pytest.mark.asyncio
    async def test_job_that_fails_once_is_redelivered_and_succeeds_on_retry(self):
        queue = LocalJobQueue(visibility_timeout=30.0, max_retries=3)
        run_audit = _FakeRunAudit(fail_times=1)
        worker = AuditWorker(queue=queue, run_audit=run_audit)
        job = _job()

        consume_task = asyncio.create_task(worker._consume_jobs())
        try:
            await queue.enqueue(job)
            await _wait_until(lambda: len(run_audit.process_calls) >= 2)
            # da' tempo do segundo ack() (bem-sucedido) ser processado.
            await _wait_until(lambda: queue._queue.empty() and queue._dead_letters.empty())
        finally:
            await _cancel(consume_task)

        assert len(run_audit.process_calls) == 2
        assert all(call[0] == job.run_id for call in run_audit.process_calls)

    @pytest.mark.asyncio
    async def test_two_concurrent_workers_never_process_the_same_job_twice(self):
        # Fase 5, secao 3.1, quarto caso de teste — a spec classifica isso
        # como garantia da propria fila (entrega exactly-once por item de
        # um asyncio.Queue entre consumidores concorrentes), nao de logica
        # do AuditWorker; testado aqui porque LocalJobQueue torna isso
        # barato de verificar sem infraestrutura externa.
        queue = LocalJobQueue(visibility_timeout=30.0, max_retries=3)
        run_audit = _FakeRunAudit(fail_times=0)
        worker_a = AuditWorker(queue=queue, run_audit=run_audit)
        worker_b = AuditWorker(queue=queue, run_audit=run_audit)
        job = _job()

        task_a = asyncio.create_task(worker_a._consume_jobs())
        task_b = asyncio.create_task(worker_b._consume_jobs())
        try:
            await queue.enqueue(job)
            await _wait_until(lambda: len(run_audit.process_calls) >= 1)
            # espera extra para dar chance de um bug fazer o segundo worker
            # tambem processar, se a garantia de exclusividade nao valesse.
            await asyncio.sleep(0.1)
        finally:
            await _cancel(task_a, task_b)

        assert len(run_audit.process_calls) == 1


class TestDeadLetterHandling:
    @pytest.mark.asyncio
    async def test_job_exhausting_retries_is_marked_failed_with_max_retries_exceeded(self):
        queue = LocalJobQueue(visibility_timeout=30.0, max_retries=1)
        run_audit = _FakeRunAudit(fail_times=999)  # sempre falha
        worker = AuditWorker(queue=queue, run_audit=run_audit)
        job = _job()

        jobs_task = asyncio.create_task(worker._consume_jobs())
        dlq_task = asyncio.create_task(worker._consume_dead_letters())
        try:
            await queue.enqueue(job)
            await _wait_until(lambda: len(run_audit.mark_failed_calls) >= 1)
        finally:
            await _cancel(jobs_task, dlq_task)

        assert run_audit.mark_failed_calls == [
            (job.run_id, job.tenant, MAX_RETRIES_EXCEEDED_REASON)
        ]
