"""Fase 8, secao 0.3 -- InterpretAuditCommandUseCase.

Teste "fino" de proposito (o use case e' uma casca sobre CommandInterpreterPort):
so' confirma delegacao correta e o requisito de seguranca da secao 0.3 --
nunca dispara RunAuditUseCase.start() nem qualquer outra acao.
"""

from __future__ import annotations

import pytest

from auditor.application.use_cases.interpret_audit_command import InterpretAuditCommandUseCase
from auditor.domain.errors import ContextBrokerUnavailableError
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


class _FakeContextBroker:
    def __init__(self, types=None, error=None):
        self._types = types or []
        self._error = error
        self.calls: list[Tenant] = []

    async def list_entity_types(self, tenant):
        self.calls.append(tenant)
        if self._error:
            raise self._error
        return self._types


class TestInterpretAuditCommandUseCase:
    @pytest.mark.asyncio
    async def test_delegates_to_the_interpreter_port_and_returns_its_result_unchanged(self):
        expected = AuditCommandInterpretation(
            entity_type="Streetlight", entity_id=None, confidence=0.85, raw_command="audite os postes"
        )
        interpreter = _FakeInterpreter(expected)
        use_case = InterpretAuditCommandUseCase(interpreter=interpreter, context_broker=_FakeContextBroker())

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
        use_case = InterpretAuditCommandUseCase(interpreter=interpreter, context_broker=_FakeContextBroker())

        await use_case.execute(_TENANT, "audite os postes")

        assert not hasattr(use_case, "_run_audit_use_case")
        assert len(interpreter.received) == 1


class TestDiscoveryIntent:
    @pytest.mark.asyncio
    async def test_audit_intent_never_queries_the_context_broker(self):
        expected = AuditCommandInterpretation(
            entity_type="Streetlight", entity_id=None, confidence=0.9, raw_command="audite os postes"
        )
        interpreter = _FakeInterpreter(expected)
        broker = _FakeContextBroker()
        use_case = InterpretAuditCommandUseCase(interpreter=interpreter, context_broker=broker)

        result = await use_case.execute(_TENANT, "audite os postes")

        assert result is expected
        assert broker.calls == []

    @pytest.mark.asyncio
    async def test_discovery_intent_returns_types_listed_by_the_context_broker(self):
        interpretation = AuditCommandInterpretation(
            entity_type=None,
            entity_id=None,
            confidence=0.9,
            raw_command="quais entidades existem?",
            intent="discovery",
        )
        interpreter = _FakeInterpreter(interpretation)
        broker = _FakeContextBroker(types=["Streetlight", "AirQualityObserved"])
        use_case = InterpretAuditCommandUseCase(interpreter=interpreter, context_broker=broker)

        result = await use_case.execute(_TENANT, "quais entidades existem?")

        assert result.intent == "discovery"
        assert result.discovered_types == ("Streetlight", "AirQualityObserved")
        assert result.broker_reachable is True
        assert result.raw_command == "quais entidades existem?"
        assert result.confidence == 0.9
        assert broker.calls == [_TENANT]

    @pytest.mark.asyncio
    async def test_discovery_intent_with_unreachable_broker_flags_it_without_raising(self):
        interpretation = AuditCommandInterpretation(
            entity_type=None,
            entity_id=None,
            confidence=0.9,
            raw_command="quais entidades existem?",
            intent="discovery",
        )
        interpreter = _FakeInterpreter(interpretation)
        broker = _FakeContextBroker(error=ContextBrokerUnavailableError("Orion inacessivel"))
        use_case = InterpretAuditCommandUseCase(interpreter=interpreter, context_broker=broker)

        result = await use_case.execute(_TENANT, "quais entidades existem?")

        assert result.discovered_types == ()
        assert result.broker_reachable is False
        assert result.intent == "discovery"

    @pytest.mark.asyncio
    async def test_discovery_intent_with_empty_broker_is_reachable_with_no_types(self):
        interpretation = AuditCommandInterpretation(
            entity_type=None,
            entity_id=None,
            confidence=0.9,
            raw_command="quais entidades existem?",
            intent="discovery",
        )
        interpreter = _FakeInterpreter(interpretation)
        broker = _FakeContextBroker(types=[])
        use_case = InterpretAuditCommandUseCase(interpreter=interpreter, context_broker=broker)

        result = await use_case.execute(_TENANT, "quais entidades existem?")

        assert result.discovered_types == ()
        assert result.broker_reachable is True
