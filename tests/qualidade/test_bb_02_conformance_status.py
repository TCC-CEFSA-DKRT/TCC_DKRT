"""Caixa-preta: ConformanceStatus.derive (RF-02) — tabela de decisao.

Condicoes: C1 = modelo encontrado no catalogo; C2 = existe violacao ERROR;
C3 = existem violacoes, todas WARNING/INFO. Acao: status derivado.

 Regra | C1 | C2 | C3 | Status esperado
 ------+----+----+----+----------------
  R1   | N  | -  | -  | no_model_found   (violacoes irrelevantes)
  R2   | S  | N  | N  | conformant       (sem violacoes)
  R3   | S  | N  | S  | partial          (so' WARNING)
  R4   | S  | N  | S  | partial          (so' INFO)
  R5   | S  | S  | -  | non_conformant   (so' ERROR)
  R6   | S  | S  | -  | non_conformant   (ERROR + WARNING)
Combinacoes impossiveis (C2=S e C3=S ao mesmo tempo) foram eliminadas."""

from __future__ import annotations

import pytest

from auditor.domain.entities.violation import DetectionSource, Violation, ViolationSeverity
from auditor.domain.value_objects.conformance_status import ConformanceStatus

from .casos import Caso, param

_PRE = "Nenhuma (função pura de domínio)."
_DESC = "Chamar ConformanceStatus.derive(violacoes, model_found=...)."


def _v(sev: ViolationSeverity) -> Violation:
    return Violation("attr", sev, "regra", None, None, "msg", DetectionSource.STRUCTURAL)


E, W, I = ViolationSeverity.ERROR, ViolationSeverity.WARNING, ViolationSeverity.INFO
CS = ConformanceStatus

TABELA = [
    (Caso("CT-STA-01", "RF-02", "TD", "R1: modelo inexistente, sem violações", _DESC, _PRE, "model_found=N; violações=[]", "no_model_found", "Alta"),
     False, [], CS.NO_MODEL_FOUND),
    (Caso("CT-STA-02", "RF-02", "TD", "R1: modelo inexistente ignora violações", _DESC, _PRE, "model_found=N; violações=[ERROR]", "no_model_found", "Alta"),
     False, [E], CS.NO_MODEL_FOUND),
    (Caso("CT-STA-03", "RF-02", "TD", "R2: modelo existe, sem violações", _DESC, _PRE, "model_found=S; violações=[]", "conformant", "Alta"),
     True, [], CS.CONFORMANT),
    (Caso("CT-STA-04", "RF-02", "TD", "R3: apenas WARNING", _DESC, _PRE, "model_found=S; violações=[WARNING]", "partial"),
     True, [W], CS.PARTIAL),
    (Caso("CT-STA-05", "RF-02", "TD", "R4: apenas INFO", _DESC, _PRE, "model_found=S; violações=[INFO]", "partial"),
     True, [I], CS.PARTIAL),
    (Caso("CT-STA-06", "RF-02", "TD", "R5: apenas ERROR", _DESC, _PRE, "model_found=S; violações=[ERROR]", "non_conformant", "Alta"),
     True, [E], CS.NON_CONFORMANT),
    (Caso("CT-STA-07", "RF-02", "TD", "R6: ERROR junto com WARNING e INFO", _DESC, _PRE, "model_found=S; violações=[WARNING, ERROR, INFO]", "non_conformant (ERROR domina, independe da ordem)", "Alta"),
     True, [W, E, I], CS.NON_CONFORMANT),
]


@pytest.mark.parametrize("caso,model_found,severidades,esperado", [param(*t) for t in TABELA])
def test_tabela_de_decisao(caso, model_found, severidades, esperado):
    status = ConformanceStatus.derive([_v(s) for s in severidades], model_found=model_found)

    assert status is esperado


def test_aceita_qualquer_iterable_de_violacoes():
    # Entrada de classe distinta: gerador em vez de lista (contrato: Iterable).
    gerador = (_v(s) for s in [W])

    assert ConformanceStatus.derive(gerador, model_found=True) is CS.PARTIAL


CASOS = [t[0] for t in TABELA]
