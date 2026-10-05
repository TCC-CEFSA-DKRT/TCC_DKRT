"""InterpretAuditCommandUseCase — ver .cursor/specs/fase8.spec.md, secao 0.3.

So' interpreta; NUNCA chama RunAuditUseCase.start() nem qualquer outra
acao — quem decide confirmar e disparar a auditoria de verdade e' a
interacao do usuario na tela "Natural Language" (Fase 8, secao 6), nunca o
backend sozinho. `tenant` e' recebido para manter o mesmo formato de
autorizacao/observabilidade dos demais use cases (Fase 4/5).
"""

from __future__ import annotations

from dataclasses import replace

from auditor.domain.errors import ContextBrokerUnavailableError
from auditor.domain.ports.command_interpreter_port import (
    AuditCommandInterpretation,
    CommandInterpreterPort,
)
from auditor.domain.ports.context_broker_port import ContextBrokerPort
from auditor.domain.value_objects.tenant import Tenant


class InterpretAuditCommandUseCase:
    def __init__(self, interpreter: CommandInterpreterPort, context_broker: ContextBrokerPort) -> None:
        self._interpreter = interpreter
        self._context_broker = context_broker

    async def execute(self, tenant: Tenant, command_text: str) -> AuditCommandInterpretation:
        interpretation = await self._interpreter.interpret(command_text)
        if interpretation.intent != "discovery":
            return interpretation
        try:
            types = await self._context_broker.list_entity_types(tenant)
        except ContextBrokerUnavailableError:
            return replace(interpretation, discovered_types=(), broker_reachable=False)
        return replace(interpretation, discovered_types=tuple(types), broker_reachable=True)
