"""Caixa-branca: ramos do StructuralValidator que os testes de dominio nao
exerciam (cobertura de comandos/ramos, RF-01). Cada caso mira uma linha ou
decisao especifica do codigo-fonte:

  - `continue` de campo obrigatorio que tambem esta numa clausula anyOf
    (`if field in conditional_fields`);
  - tipo esperado desconhecido no schema (`expected_type not in _JSON_TYPE_PYTHON`);
  - `_json_type_name` para object / array / outro tipo;
  - clausula anyOf parcialmente satisfeita (so' o campo que falta e' reportado)."""

from __future__ import annotations

import pytest

from auditor.domain.services.structural_validator import StructuralValidator

from .casos import Caso, param

_PRE = "Schema de teste construído no próprio caso; validador sem estado."
_DESC = "Chamar StructuralValidator().validate(entidade, schema) e inspecionar a lista de violações."


def _c(id, nome, dados, esperado, prio="Média"):
    return Caso(id, "RF-01", "CB", nome, _DESC, _PRE, dados, esperado, prio)


_ANYOF_DUP = {"required": ["location"], "anyOf": [{"required": ["location"]}, {"required": ["address"]}]}
_ANYOF_PARCIAL = {"required": [], "anyOf": [{"required": ["a", "b"]}, {"required": ["c"]}]}
_TIPO_STR = {"properties": {"x": {"type": "string"}}}

# (caso, entidade, schema, [(regra, atributo, found)])
RAMOS = [
    (_c("CT-WB-13", "Obrigatório que também está no anyOf não é reportado em duplicidade", "required=[location]; anyOf location|address; entidade vazia", "1 violação (location), não 2"),
     {}, _ANYOF_DUP, [("required_property_missing", "location", "absent")]),
    (_c("CT-WB-14", "Tipo esperado desconhecido no schema é ignorado", "type='null' (não mapeado) e valor 1", "Nenhuma violação"),
     {"x": 1}, {"properties": {"x": {"type": "null"}}}, []),
    (_c("CT-WB-15", "Valor dict onde se espera string → found='object'", "x={'a': 1}", "type_mismatch com found=object"),
     {"x": {"a": 1}}, _TIPO_STR, [("type_mismatch", "x", "object")]),
    (_c("CT-WB-16", "Valor lista onde se espera string → found='array'", "x=[1]", "type_mismatch com found=array"),
     {"x": [1]}, _TIPO_STR, [("type_mismatch", "x", "array")]),
    (_c("CT-WB-17", "Valor de tipo exótico → found = nome da classe Python", "x=b'abc'", "type_mismatch com found=bytes"),
     {"x": b"abc"}, _TIPO_STR, [("type_mismatch", "x", "bytes")]),
    (_c("CT-WB-18", "Booleano onde se espera string → found='boolean'", "x=True", "type_mismatch com found=boolean"),
     {"x": True}, _TIPO_STR, [("type_mismatch", "x", "boolean")]),
    (_c("CT-WB-19", "anyOf parcialmente satisfeito: só o campo ausente é reportado", "a presente, b ausente; c ausente", "1 violação: b (1ª alternativa)"),
     {"a": 1}, _ANYOF_PARCIAL, [("required_property_missing", "b", "absent")]),
    (_c("CT-WB-20", "anyOf satisfeito pela 2ª alternativa", "c presente", "Nenhuma violação"),
     {"c": 1}, _ANYOF_PARCIAL, []),
]


@pytest.mark.parametrize("caso,entidade,schema,esperado", [param(*t) for t in RAMOS])
def test_ramos_do_validador(caso, entidade, schema, esperado):
    violacoes = StructuralValidator().validate(entidade, schema)

    assert sorted((v.rule, v.attribute_path, v.found) for v in violacoes) == sorted(esperado)


CASOS = [t[0] for t in RAMOS]
