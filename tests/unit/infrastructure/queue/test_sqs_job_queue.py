"""Fase 5 — SqsJobQueue. Ver .cursor/specs/fase5.spec.md, secao 2.3.

Testado via moto (simulacao de SQS) — teste de integracao contra SQS real
fica reservado para a Fase 9 (deploy), nao bloqueia esta fase. Escopo
minimo explicito do spec: enqueue() precisa mandar o run_id serializado e
nenhum dado sensivel de tenant alem do necessario para roteamento. Os
testes de consume()/ack()/nack() aqui sao um extra barato (moto simula bem
o suficiente), nao um requisito desta fase.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import boto3
import pytest
from moto import mock_aws

from auditor.domain.entities.audit_job import AuditJob
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.queue.sqs_job_queue import SqsJobQueue

_TENANT = Tenant(fiware_service="openiot", fiware_service_path="/")
_NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _job() -> AuditJob:
    return AuditJob(
        run_id=uuid4(),
        tenant=_TENANT,
        entity_type=EntityType("Streetlight"),
        entity_id="urn:1",
        enqueued_at=_NOW,
    )


class TestEnqueue:
    @pytest.mark.asyncio
    async def test_enqueue_sends_run_id_and_no_broker_secrets(self):
        with mock_aws():
            client = boto3.client("sqs", region_name="us-east-1")
            queue_url = client.create_queue(QueueName="audit-jobs")["QueueUrl"]
            queue = SqsJobQueue(client, queue_url)
            job = _job()

            await queue.enqueue(job)

            received = client.receive_message(
                QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=1
            )
            messages = received.get("Messages", [])
            assert len(messages) == 1
            body = json.loads(messages[0]["Body"])

            assert body["run_id"] == str(job.run_id)
            assert body["fiware_service"] == _TENANT.fiware_service
            assert body["fiware_service_path"] == _TENANT.fiware_service_path
            assert body["entity_type"] == "Streetlight"
            assert body["entity_id"] == "urn:1"
            # Nunca vaza segredo de conexao do broker do cliente — o
            # dominio nem modela isso em Tenant para comecar. Confirmamos
            # aqui que as chaves da mensagem sao exatamente as esperadas,
            # nada extra vazando por acidente.
            assert set(body.keys()) == {
                "run_id", "fiware_service", "fiware_service_path",
                "entity_type", "entity_id", "enqueued_at",
            }

    @pytest.mark.asyncio
    async def test_enqueue_round_trips_through_the_same_deserialization_used_by_consume(self):
        with mock_aws():
            client = boto3.client("sqs", region_name="us-east-1")
            queue_url = client.create_queue(QueueName="audit-jobs")["QueueUrl"]
            queue = SqsJobQueue(client, queue_url, wait_time_seconds=0)
            job = _job()

            await queue.enqueue(job)
            handle = await queue.consume().__anext__()

            assert handle.job == job
            await handle.ack()


class TestConsumeAckNack:
    @pytest.mark.asyncio
    async def test_ack_deletes_the_message(self):
        with mock_aws():
            client = boto3.client("sqs", region_name="us-east-1")
            queue_url = client.create_queue(QueueName="audit-jobs")["QueueUrl"]
            queue = SqsJobQueue(client, queue_url, wait_time_seconds=0)
            await queue.enqueue(_job())

            handle = await queue.consume().__anext__()
            await handle.ack()

            empty = client.receive_message(
                QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=0
            )
            assert "Messages" not in empty

    @pytest.mark.asyncio
    async def test_nack_makes_the_message_immediately_visible_again(self):
        with mock_aws():
            client = boto3.client("sqs", region_name="us-east-1")
            queue_url = client.create_queue(
                QueueName="audit-jobs", Attributes={"VisibilityTimeout": "30"}
            )["QueueUrl"]
            queue = SqsJobQueue(client, queue_url, wait_time_seconds=0)
            job = _job()
            await queue.enqueue(job)

            handle = await queue.consume().__anext__()
            await handle.nack()

            redelivered = await queue.consume().__anext__()
            assert redelivered.job.run_id == job.run_id
