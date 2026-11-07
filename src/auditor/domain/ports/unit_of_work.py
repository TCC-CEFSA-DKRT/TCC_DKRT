"""UnitOfWork — ver .cursor/specs/fase3.spec.md, secao 7."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol

from auditor.domain.ports.audit_repository_port import AuditRepositoryPort


class UnitOfWork(Protocol):
    @property
    def audits(self) -> AuditRepositoryPort:
        """Repositorio da transacao aberta; so existe dentro do `async with`."""
        ...

    async def __aenter__(self) -> "UnitOfWork": ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Commit se saiu sem excecao, rollback se houve excecao."""
        ...
