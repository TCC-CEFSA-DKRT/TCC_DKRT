"""Caixa-preta: StructuralValidator.validate (RF-01).

Tecnicas: particionamento em classes de equivalencia (CE) e analise de
valor-limite (AVL) sobre a faixa `minimum/maximum` de um atributo numerico.
O validador e' tratado como caixa-preta: so' entra (entidade, schema) e so'
sai a lista de violacoes (regra, severidade, atributo)."""

from __future__ import annotations

import pytest

from auditor.domain.entities.violation import ViolationSeverity
from auditor.domain.services.structural_validator import StructuralValidator

from .casos import Caso, param

SCHEMA = {
    "required": ["id", "type", "status"],
    "properties": {
        "id": {"type": "string"},
        "type": {"type": "string"},
        "status": {"type": "string", "enum": ["ok", "defectiveLamp", "columnIssue"]},
        "dateLastLampChange": {"type": "string", "format": "date-time"},
        "lanternHeight": {"type": "number", "minimum": 0, "maximum": 20},
        "circuitNumber": {"type": "integer"},
    },
    "additionalProperties": False,
}

SCHEMA_ANYOF = {
    "required": ["id", "type"],
    "properties": {"id": {"type": "string"}, "type": {"type": "string"}},
    "anyOf": [{"required": ["location"]}, {"required": ["address"]}],
}

BASE = {"id": "urn:ngsi-ld:Streetlight:001", "type": "Streetlight", "status": "ok"}

_PRE = "Schema Streetlight de teste carregado; validador instanciado."
_DESC = "Chamar StructuralValidator().validate(entidade, schema) e inspecionar as violacoes."


def _c(id, req, tec, nome, dados, esperado, prio="Média", defeito=None):
    return Caso(id, req, tec, nome, _DESC, _PRE, dados, esperado, prio, defeito)


# (caso, entidade, schema, [(regra, atributo, severidade)])
E, W = ViolationSeverity.ERROR, ViolationSeverity.WARNING
CASOS_CE = [
    (_c("CT-VAL-01", "RF-01", "CE", "Entidade totalmente valida", "id,type,status=ok", "Nenhuma violação", "Alta"),
     BASE, SCHEMA, []),
    (_c("CT-VAL-02", "RF-01", "CE", "Obrigatório ausente", "sem 'status'", "required_property_missing em status (ERROR)", "Alta"),
     {"id": "1", "type": "T"}, SCHEMA, [("required_property_missing", "status", E)]),
    (_c("CT-VAL-03", "RF-01", "CE", "Obrigatório presente porém nulo", "status=None", "required_property_missing em status (ERROR)"),
     {**BASE, "status": None}, SCHEMA, [("required_property_missing", "status", E)]),
    (_c("CT-VAL-04", "RF-01", "CE", "Tipo errado (string onde se espera number)", "lanternHeight='alta'", "type_mismatch em lanternHeight (ERROR)", "Alta"),
     {**BASE, "lanternHeight": "alta"}, SCHEMA, [("type_mismatch", "lanternHeight", E)]),
    (_c("CT-VAL-05", "RF-01", "CE", "Booleano onde se espera number", "lanternHeight=true", "type_mismatch em lanternHeight (ERROR)"),
     {**BASE, "lanternHeight": True}, SCHEMA, [("type_mismatch", "lanternHeight", E)]),
    (_c("CT-VAL-06", "RF-01", "CE", "Valor fora do enum", "status='quebrado'", "enum_violation em status (ERROR)", "Alta"),
     {**BASE, "status": "quebrado"}, SCHEMA, [("enum_violation", "status", E)]),
    (_c("CT-VAL-07", "RF-01", "CE", "date-time inválido (texto livre)", "dateLastLampChange='ontem'", "format_invalid (ERROR)"),
     {**BASE, "dateLastLampChange": "ontem"}, SCHEMA, [("format_invalid", "dateLastLampChange", E)]),
    (_c("CT-VAL-08", "RF-01", "CE", "date-time válido com offset", "dateLastLampChange='2026-10-01T10:00:00Z'", "Nenhuma violação"),
     {**BASE, "dateLastLampChange": "2026-10-01T10:00:00Z"}, SCHEMA, []),
    (_c("CT-VAL-09", "RF-01", "CE", "Propriedade fora do schema", "campoExtra='x'", "unexpected_property (WARNING)"),
     {**BASE, "campoExtra": "x"}, SCHEMA, [("unexpected_property", "campoExtra", W)]),
    (_c("CT-VAL-10", "RF-01", "CE", "Várias violações simultâneas", "sem status + altura em texto + extra",
        "3 violações: missing, type_mismatch, unexpected_property", "Alta"),
     {"id": "1", "type": "T", "lanternHeight": "x", "extra": 1}, SCHEMA,
     [("required_property_missing", "status", E), ("type_mismatch", "lanternHeight", E), ("unexpected_property", "extra", W)]),
    (_c("CT-VAL-11", "RF-01", "CE", "Obrigatório alternativo (anyOf) satisfeito por location", "location presente", "Nenhuma violação"),
     {"id": "1", "type": "T", "location": {}}, SCHEMA_ANYOF, []),
    (_c("CT-VAL-12", "RF-01", "CE", "Obrigatório alternativo (anyOf) satisfeito por address", "address presente", "Nenhuma violação"),
     {"id": "1", "type": "T", "address": {}}, SCHEMA_ANYOF, []),
    (_c("CT-VAL-13", "RF-01", "CE", "Nenhuma alternativa do anyOf satisfeita", "sem location e sem address",
        "Reporta só a 1ª alternativa: location ausente (ERROR)"),
     {"id": "1", "type": "T"}, SCHEMA_ANYOF, [("required_property_missing", "location", E)]),
]


@pytest.mark.parametrize("caso,entidade,schema,esperado", [param(*t) for t in CASOS_CE])
def test_classes_de_equivalencia(caso, entidade, schema, esperado):
    violacoes = StructuralValidator().validate(entidade, schema)

    obtido = sorted((v.rule, v.attribute_path, v.severity) for v in violacoes)
    assert obtido == sorted(esperado)


# --- Analise de valor-limite: lanternHeight in [0, 20] (number) ------------
# Fronteiras: min-, min, min+, nominal, max-, max, max+
_AVL = [
    ("CT-VAL-14", -0.001, True, "limite inferior − (abaixo de 0)", None),
    ("CT-VAL-15", 0, False, "limite inferior (0)", None),
    ("CT-VAL-16", 0.001, False, "limite inferior + (logo acima de 0)", None),
    ("CT-VAL-17", 10, False, "valor nominal (10)", None),
    ("CT-VAL-18", 19.999, False, "limite superior − (logo abaixo de 20)", None),
    ("CT-VAL-19", 20, False, "limite superior (20)", None),
    ("CT-VAL-20", 20.001, True, "limite superior + (acima de 20)", None),
]
CASOS_AVL = [
    (Caso(i, "RF-01", "AVL", f"lanternHeight no {nome}", _DESC, _PRE, f"lanternHeight={v}",
          "value_out_of_range (ERROR)" if viola else "Nenhuma violação", "Alta", d), v, viola)
    for i, v, viola, nome, d in _AVL
]


@pytest.mark.parametrize("caso,valor,deve_violar", [param(c, v, x) for c, v, x in CASOS_AVL])
def test_valor_limite_da_faixa(caso, valor, deve_violar):
    violacoes = StructuralValidator().validate({**BASE, "lanternHeight": valor}, SCHEMA)

    regras = [v.rule for v in violacoes]
    assert regras == (["value_out_of_range"] if deve_violar else [])


# --- Defeitos encontrados na analise exploratoria (xfail estrito) -----------
_PRE_D = _PRE
CASOS_DEFEITO = [
    (Caso("CT-VAL-21", "RF-01", "CE", "Booleano aceito como integer", _DESC, _PRE_D,
          "circuitNumber=true (schema integer)", "type_mismatch (para number o booleano já é rejeitado)", "Média", "D-03"),
     {**BASE, "circuitNumber": True}, "type_mismatch"),
    (Caso("CT-VAL-22", "RF-01", "CE", "Data sem hora aceita como date-time", _DESC, _PRE_D,
          "dateLastLampChange='2026-10-01'", "format_invalid (RFC 3339 exige data e hora)", "Média", "D-04"),
     {**BASE, "dateLastLampChange": "2026-10-01"}, "format_invalid"),
    (Caso("CT-VAL-23", "RF-01", "AVL", "NaN passa na checagem de faixa", _DESC, _PRE_D,
          "lanternHeight=NaN", "value_out_of_range (NaN não é um número válido na faixa)", "Baixa", "D-05"),
     {**BASE, "lanternHeight": float("nan")}, "value_out_of_range"),
]


@pytest.mark.parametrize("caso,entidade,regra_esperada", [param(*t) for t in CASOS_DEFEITO])
def test_defeitos_conhecidos(caso, entidade, regra_esperada):
    regras = [v.rule for v in StructuralValidator().validate(entidade, SCHEMA)]

    assert regra_esperada in regras


CASOS = [t[0] for t in CASOS_CE] + [t[0] for t in CASOS_AVL] + [t[0] for t in CASOS_DEFEITO]
