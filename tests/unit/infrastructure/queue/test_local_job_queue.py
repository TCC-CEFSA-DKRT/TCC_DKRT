"""Fase 5 — LocalJobQueue. Ver .cursor/specs/fase5.spec.md, secao 2.1
(contrato, roda para as duas implementacoes de JobQueuePort) e 2.2 (dev,
sem infraestrutura)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from auditor.domain.entities.audit_job import AuditJob
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.queue.local_job_queue import LocalJobQueue

_TENANT = Tenant(fiware_service="openiot", fiware_service_path="/")
_NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _job(entity_id: str | None = None) -> AuditJob:
    return AuditJob(
        run_id=uuid4(),
        tenant=_TENANT,
        entity_type=EntityType("Streetlight"),
        entity_id=entity_id,
        enqueued_at=_NOW,
    )


async def _receive_one(queue: LocalJobQueue):
    async for handle in queue.consume():
        return handle


class TestContract:
    @pytest.mark.asyncio
    async def test_enqueued_job_is_delivered_with_the_same_payload(self):
        queue = LocalJobQueue()
        job = _job()
        await queue.enqueue(job)

        handle = await _receive_one(queue)

        assert handle.job == job
        await handle.ack()

    @pytest.mark.asyncio
    async def test_ack_removes_the_job_so_it_is_never_delivered_again(self):
        queue = LocalJobQueue(visibility_timeout=0.05)
        await queue.enqueue(_job())

        handle = await _receive_one(queue)
        await handle.ack()

        # espera mais que o visibility_timeout — se o ack() nao tivesse
        # funcionado, o job reapareceria na fila.
        await asyncio.sleep(0.15)
        assert queue._queue.empty()
        assert queue._dead_letters.empty()

    @pytest.mark.asyncio
    async def test_nack_makes_the_job_available_for_redelivery(self):
        queue = LocalJobQueue(visibility_timeout=30.0, max_retries=3)
        job = _job()
        await queue.enqueue(job)

        first_handle = await _receive_one(queue)
        await first_handle.nack()

        second_handle = await _receive_one(queue)
        assert second_handle.job == job
        await second_handle.ack()

    @pytest.mark.asyncio
    async def test_expired_visibility_timeout_triggers_redelivery_like_an_explicit_nack(self):
        queue = LocalJobQueue(visibility_timeout=0.05, max_retries=3)
        job = _job()
        await queue.enqueue(job)

        first_handle = await _receive_one(queue)
        # nem ack() nem nack() chamado — so' esperamos o timeout expirar.
        await asyncio.sleep(0.15)

        second_handle = await _receive_one(queue)
        assert second_handle.job == job
        await second_handle.ack()

    @pytest.mark.asyncio
    async def test_job_that_exceeds_max_retries_goes_to_dead_letter_queue_instead_of_being_redelivered(self):
        queue = LocalJobQueue(visibility_timeout=30.0, max_retries=3)
        job = _job()
        await queue.enqueue(job)

        for _ in range(3):
            handle = await _receive_one(queue)
            await handle.nack()

        # a fila principal deve estar vazia agora — o job foi para a DLQ,
        # nao reentregue uma quarta vez.
        assert queue._queue.empty()

        dead_job = await asyncio.wait_for(queue.consume_dead_letters().__anext__(), timeout=1.0)
        assert dead_job == job


class TestLocalJobQueueDevScope:
    @pytest.mark.asyncio
    async def test_500_jobs_enqueued_rapidly_are_all_delivered_without_loss(self):
        queue = LocalJobQueue(visibility_timeout=30.0)
        jobs = [_job(entity_id=str(i)) for i in range(500)]
        for job in jobs:
            await queue.enqueue(job)

        received: list[AuditJob] = []
        async for handle in queue.consume():
            received.append(handle.job)
            await handle.ack()
            if len(received) == 500:
                break

        assert len(received) == 500
        assert {j.entity_id for j in received} == {j.entity_id for j in jobs}
