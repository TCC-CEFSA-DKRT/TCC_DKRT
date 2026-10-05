"""AuditJob — ver .cursor/specs/fase5.spec.md, secao 1.

Um job por RUN inteiro, nunca por entidade — reentrega (at-least-once,
padrao SQS) reprocessa o run inteiro. Isso e' seguro porque a validacao
estrutural e' pura e `append_report` ja' e' idempotente por
(run_id, entity_id) desde a Fase 3 — nenhum mecanismo novo de deduplicacao
e' necessario aqui.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant
from uuid import UUID


@dataclass(frozen=True)
class AuditJob:
    run_id: UUID
    tenant: Tenant
    entity_type: EntityType | None
    entity_id: str | None
    enqueued_at: datetime
