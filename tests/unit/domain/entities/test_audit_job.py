"""Fase 5 — AuditJob. Ver .cursor/specs/fase5.spec.md, secao 1."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from auditor.domain.entities.audit_job import AuditJob
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant

_TENANT = Tenant(fiware_service="openiot", fiware_service_path="/")


def test_audit_job_carries_everything_needed_to_reprocess_a_run_without_a_db_lookup():
    run_id = uuid4()
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)

    job = AuditJob(
        run_id=run_id,
        tenant=_TENANT,
        entity_type=EntityType("Streetlight"),
        entity_id="urn:1",
        enqueued_at=now,
    )

    assert job.run_id == run_id
    assert job.tenant == _TENANT
    assert job.entity_type == EntityType("Streetlight")
    assert job.entity_id == "urn:1"
    assert job.enqueued_at == now


def test_audit_job_accepts_none_for_broad_audits():
    job = AuditJob(
        run_id=uuid4(),
        tenant=_TENANT,
        entity_type=None,
        entity_id=None,
        enqueued_at=datetime.now(timezone.utc),
    )

    assert job.entity_type is None
    assert job.entity_id is None


def test_audit_job_is_frozen():
    job = AuditJob(
        run_id=uuid4(),
        tenant=_TENANT,
        entity_type=None,
        entity_id=None,
        enqueued_at=datetime.now(timezone.utc),
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        job.entity_id = "urn:changed"  # type: ignore[misc]
