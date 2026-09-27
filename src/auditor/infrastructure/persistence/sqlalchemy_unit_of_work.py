"""SqlAlchemyUnitOfWork — ver .cursor/specs/fase3.spec.md, secao 7.

Uma conexao e uma transacao por bloco `async with` — e' isso que permite
reverter tudo se algo no meio do bloco falhar. O repository nunca abre suas
proprias transacoes (ver postgres_audit_repository.py); ele so opera sobre a
conexao que este UnitOfWork fornece em `__aenter__`.
"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncTransaction

from auditor.infrastructure.persistence.postgres_audit_repository import PostgresAuditRepository


class SqlAlchemyUnitOfWork:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._connection: AsyncConnection | None = None
        self._transaction: AsyncTransaction | None = None
        self.audits: PostgresAuditRepository | None = None

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self._connection = await self._engine.connect()
        self._transaction = await self._connection.begin()
        self.audits = PostgresAuditRepository(self._connection)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self._connection is not None and self._transaction is not None
        try:
            if exc_type is None:
                await self._transaction.commit()
            else:
                await self._transaction.rollback()
        finally:
            await self._connection.close()
            self._connection = None
            self._transaction = None
            self.audits = None
