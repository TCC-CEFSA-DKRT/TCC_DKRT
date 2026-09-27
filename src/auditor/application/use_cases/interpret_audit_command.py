"""InterpretAuditCommandUseCase — ver .cursor/specs/fase8.spec.md, secao 0.3.

So' interpreta; NUNCA chama RunAuditUseCase.start() nem qualquer outra
acao — quem decide confirmar e disparar a auditoria de verdade e' a
interacao do usuario na tela "Natural Language" (Fase 8, secao 6), nunca o
backend sozinho. `tenant` e' recebido para manter o mesmo formato de
autorizacao/observabilidade dos demais use cases (Fase 4/5), ainda que a
interpretacao em si nao filtre nada por tenant hoje.
"""

from __future__ import annotations

from auditor.domain.ports.command_interpreter_port import (
    AuditCommandInterpretation,
    CommandInterpreterPort,
)
from auditor.domain.value_objects.tenant import Tenant


class InterpretAuditCommandUseCase:
    def __init__(self, interpreter: CommandInterpreterPort) -> None:
        self._interpreter = interpreter

    async def execute(self, tenant: Tenant, command_text: str) -> AuditCommandInterpretation:
        return await self._interpreter.interpret(command_text)
