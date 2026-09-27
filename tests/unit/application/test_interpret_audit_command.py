"""Fase 8, secao 0.3 -- InterpretAuditCommandUseCase.

Teste "fino" de proposito (o use case e' uma casca sobre CommandInterpreterPort):
so' confirma delegacao correta e o requisito de seguranca da secao 0.3 --
nunca dispara RunAuditUseCase.start() nem qualquer outra acao.
"""

from __future__ import annotations

import pytest

from auditor.application.use_cases.interpret_audit_command import InterpretAuditCommandUseCase
from auditor.domain.ports.command_interpreter_port import AuditCommandInterpretation
from auditor.domain.value_objects.tenant import Tenant

_TENANT = Tenant(fiware_service="openiot", fiware_service_path="/")


class _FakeInterpreter:
    def __init__(self, result: AuditCommandInterpretation):
        self._result = result
        self.received: list[str] = []

    async def interpret(self, command_text: str) -> AuditCommandInterpretation:
        self.received.append(command_text)
        return self._result


class TestInterpretAuditCommandUseCase:
    @pytest.mark.asyncio
    async def test_delegates_to_the_interpreter_port_and_returns_its_result_unchanged(self):
        expected = AuditCommandInterpretation(
            entity_type="Streetlight", entity_id=None, confidence=0.85, raw_command="audite os postes"
        )
        interpreter = _FakeInterpreter(expected)
        use_case = InterpretAuditCommandUseCase(interpreter=interpreter)

        result = await use_case.execute(_TENANT, "audite os postes")

        assert result is expected
        assert interpreter.received == ["audite os postes"]

    @pytest.mark.asyncio
    async def test_never_touches_run_audit_use_case(self):
        """Nao ha' RunAuditUseCase injetado no construtor deste use case --
        a propria assinatura ja' garante isso estaticamente. Este teste
        documenta a garantia em termos comportamentais: o unico efeito
        colateral observavel de execute() e' a chamada ao interpretador."""
        interpreter = _FakeInterpreter(
            AuditCommandInterpretation(
                entity_type="Streetlight", entity_id=None, confidence=0.9, raw_command="x"
            )
        )
        use_case = InterpretAuditCommandUseCase(interpreter=interpreter)

        await use_case.execute(_TENANT, "audite os postes")

        assert not hasattr(use_case, "_run_audit_use_case")
        assert len(interpreter.received) == 1
