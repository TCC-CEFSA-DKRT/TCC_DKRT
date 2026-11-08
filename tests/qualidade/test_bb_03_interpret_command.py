"""Caixa-preta: InterpretAuditCommandUseCase.execute (RF-03).

Tabela de decisao (condicoes sobre o que o interpretador SLM devolve) +
analise de valor-limite do limiar de confianca (MIN_CONFIDENCE_TO_CONFIRM
= 0.5). Interpretador e Context Broker sao MOCKS (AsyncMock): o teste nao
depende de Ollama nem de Orion.

 Regra | SLM ok | intencao       | tipo/confianca ok | broker ok | Resultado
 ------+--------+----------------+-------------------+-----------+---------------------------
  R1   | N      | (qualquer)     | -                 | -         | devolve como veio; nao consulta broker
  R2   | S      | out_of_scope   | -                 | -         | zera tipo/id; nao consulta broker
  R3   | S      | audit          | S                 | -         | permanece audit; nao consulta broker
  R4   | S      | audit          | N (sem tipo)      | S         | vira clarify + tipos do broker
  R5   | S      | audit          | N (conf < 0.5)    | S         | vira clarify + tipos do broker
  R6   | S      | clarify        | -                 | S         | pergunta padrao + tipos
  R7   | S      | clarify        | -                 | N         | broker_reachable=False, tipos=()
  R8   | S      | discovery      | -                 | S         | lista tipos do broker
  R9   | S      | discovery      | -                 | N         | broker_reachable=False, tipos=()"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from auditor.application.use_cases.interpret_audit_command import (
    DEFAULT_CLARIFICATION_QUESTION,
    MIN_CONFIDENCE_TO_CONFIRM,
    InterpretAuditCommandUseCase,
)
from auditor.domain.errors import ContextBrokerUnavailableError
from auditor.domain.ports.command_interpreter_port import AuditCommandInterpretation
from auditor.domain.value_objects.tenant import Tenant

from .casos import Caso, param

TENANT = Tenant(fiware_service="openiot", fiware_service_path="/")
_PRE = "Interpretador e broker substituídos por mocks (AsyncMock)."
_DESC = "Executar o caso de uso com o comando 'audite Streetlight' e a saída simulada do interpretador."
TIPOS = ["Streetlight", "Parking"]


def _interp(**kw) -> AuditCommandInterpretation:
    base = dict(entity_type="Streetlight", entity_id=None, confidence=0.9, raw_command="audite Streetlight", intent="audit")
    return AuditCommandInterpretation(**{**base, **kw})


def _caso(id, nome, dados, esperado, prio="Média"):
    return Caso(id, "RF-03", "TD", nome, _DESC, _PRE, dados, esperado, prio)


# (caso, saida_do_interpretador, broker_ok, esperado: dict de checagens)
TABELA = [
    (_caso("CT-NL-01", "R1: SLM indisponível", "interpreter_available=N", "Devolve a interpretação sem tocar no broker", "Alta"),
     _interp(interpreter_available=False, entity_type=None, confidence=0.0), True,
     dict(intent="audit", broker_chamado=False, interpreter_available=False)),
    (_caso("CT-NL-02", "R2: pedido fora do escopo", "intent=out_of_scope; tipo=Streetlight", "Zera tipo/id e não consulta o broker", "Alta"),
     _interp(intent="out_of_scope"), True,
     dict(intent="out_of_scope", entity_type=None, broker_chamado=False)),
    (_caso("CT-NL-03", "R3: auditoria clara e confiante", "intent=audit; tipo=Streetlight; conf=0.9", "Permanece audit com o tipo; não consulta o broker", "Alta"),
     _interp(), True,
     dict(intent="audit", entity_type="Streetlight", broker_chamado=False)),
    (_caso("CT-NL-04", "R4: auditoria sem tipo", "intent=audit; tipo=None", "Vira clarify e lista tipos do broker", "Alta"),
     _interp(entity_type=None), True,
     dict(intent="clarify", entity_type=None, broker_chamado=True, discovered=tuple(TIPOS), broker_reachable=True,
          pergunta=DEFAULT_CLARIFICATION_QUESTION)),
    (_caso("CT-NL-05", "R5: auditoria com confiança baixa", "intent=audit; conf=0.1", "Vira clarify e zera o tipo", "Alta"),
     _interp(confidence=0.1), True,
     dict(intent="clarify", entity_type=None, broker_chamado=True)),
    (_caso("CT-NL-06", "R6: clarify mantém a pergunta do SLM", "intent=clarify; pergunta='Qual tipo?'", "Pergunta preservada + tipos do broker"),
     _interp(intent="clarify", entity_type=None, clarification_question="Qual tipo?"), True,
     dict(intent="clarify", pergunta="Qual tipo?", broker_chamado=True, discovered=tuple(TIPOS))),
    (_caso("CT-NL-07", "R7: clarify com broker fora do ar", "intent=clarify; broker lança ContextBrokerUnavailableError", "broker_reachable=False e tipos vazios"),
     _interp(intent="clarify", entity_type=None), False,
     dict(intent="clarify", broker_chamado=True, discovered=(), broker_reachable=False)),
    (_caso("CT-NL-08", "R8: discovery com broker no ar", "intent=discovery", "Lista os tipos do broker", "Alta"),
     _interp(intent="discovery", entity_type=None), True,
     dict(intent="discovery", broker_chamado=True, discovered=tuple(TIPOS), broker_reachable=True)),
    (_caso("CT-NL-09", "R9: discovery com broker fora do ar", "intent=discovery; broker indisponível", "broker_reachable=False e tipos vazios"),
     _interp(intent="discovery", entity_type=None), False,
     dict(intent="discovery", broker_chamado=True, discovered=(), broker_reachable=False)),
]


def _montar(saida, broker_ok):
    interpretador = AsyncMock()
    interpretador.interpret.return_value = saida
    broker = AsyncMock()
    if broker_ok:
        broker.list_entity_types.return_value = TIPOS
    else:
        broker.list_entity_types.side_effect = ContextBrokerUnavailableError("fora do ar")
    return InterpretAuditCommandUseCase(interpretador, broker), interpretador, broker


@pytest.mark.asyncio
@pytest.mark.parametrize("caso,saida,broker_ok,esperado", [param(*t) for t in TABELA])
async def test_tabela_de_decisao(caso, saida, broker_ok, esperado):
    caso_de_uso, interpretador, broker = _montar(saida, broker_ok)

    r = await caso_de_uso.execute(TENANT, "audite Streetlight")

    interpretador.interpret.assert_awaited_once_with("audite Streetlight")
    assert (broker.list_entity_types.await_count > 0) is esperado["broker_chamado"]
    assert r.intent == esperado["intent"]
    if "entity_type" in esperado:
        assert r.entity_type == esperado["entity_type"]
    if "discovered" in esperado:
        assert r.discovered_types == esperado["discovered"]
    if "broker_reachable" in esperado:
        assert r.broker_reachable is esperado["broker_reachable"]
    if "pergunta" in esperado:
        assert r.clarification_question == esperado["pergunta"]
    if "interpreter_available" in esperado:
        assert r.interpreter_available is esperado["interpreter_available"]


# --- AVL do limiar de confianca (0.5): abaixo -> clarify; >= -> audit -------
_AVL = [
    ("CT-NL-10", 0.0, "clarify"), ("CT-NL-11", 0.49, "clarify"), ("CT-NL-12", 0.5, "audit"),
    ("CT-NL-13", 0.51, "audit"), ("CT-NL-14", 1.0, "audit"),
]
CASOS_AVL = [
    (Caso(i, "RF-03", "AVL", f"Confiança {c} (limiar {MIN_CONFIDENCE_TO_CONFIRM})", _DESC, _PRE,
          f"intent=audit; tipo=Streetlight; confidence={c}", f"intent={esp}", "Alta"), c, esp)
    for i, c, esp in _AVL
]


@pytest.mark.asyncio
@pytest.mark.parametrize("caso,confianca,esperado", [param(*t) for t in CASOS_AVL])
async def test_valor_limite_da_confianca(caso, confianca, esperado):
    caso_de_uso, _, _ = _montar(_interp(confidence=confianca), True)

    r = await caso_de_uso.execute(TENANT, "audite Streetlight")

    assert r.intent == esperado


CASOS = [t[0] for t in TABELA] + [t[0] for t in CASOS_AVL]
