"""UnitOfWork — ver .cursor/specs/fase3.spec.md, secao 7."""

from __future__ import annotations

from typing import Protocol

from auditor.domain.ports.audit_repository_port import AuditRepositoryPort


class UnitOfWork(Protocol):
    audits: AuditRepositoryPort

    async def __aenter__(self) -> "UnitOfWork": ...

    async def __aexit__(self, *exc: object) -> None:
        """Commit se saiu sem excecao, rollback se houve excecao."""
        ...
