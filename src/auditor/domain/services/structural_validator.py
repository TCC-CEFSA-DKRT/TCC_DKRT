"""StructuralValidator (Nivel 1) — ver .cursor/specs/fase1.spec.md, secao 3, e
docs/plano_refatoracao_v3.md, Parte III, 3.2.

Pre-condicao documentada no contrato: `entity` ja passou pelo `NgsiV2Mapper`
(Fase 4) — chega aqui como um dict plano de valores, nao o envelope NGSI-v2
({"attr": {"type":..., "value":...}}). O StructuralValidator nunca lida com o
envelope diretamente.

Decisao de design registrada aqui (nao explicitada literalmente na spec):
quando um atributo e "obrigatorio somente se outro estiver ausente" (schema
com `anyOf: [{"required": [...]}, ...]`), e NENHUMA das alternativas e
satisfeita, o validador reporta a ausencia apenas dos campos da PRIMEIRA
alternativa (a expectativa canonica) — nao a uniao de todas as alternativas.
Isso e o que faz o fixture `streetlight_non_conformant.json` (falta `location`
e nao tem `address`) produzir exatamente as duas violacoes ERROR descritas na
secao 4 do spec (uma de obrigatoriedade, uma de tipo), em vez de tres.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from auditor.domain.entities.violation import DetectionSource, Violation, ViolationSeverity

_JSON_TYPE_PYTHON: dict[str, tuple[type, ...]] = {
    "number": (int, float),
    "integer": (int,),
    "string": (str,),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
}

_ENVELOPE_FIELDS = {"id", "type"}


class StructuralValidator:
    """Compara uma entidade NGSI-v2 (ja em valores planos) contra um Smart
    Data Model schema.json. Sem I/O, sem decisao de status — so produz
    violacoes."""

    def validate(self, entity: dict[str, Any], schema: dict[str, Any]) -> list[Violation]:
        violations: list[Violation] = []
        violations.extend(self._check_required(entity, schema))
        violations.extend(self._check_properties(entity, schema))
        violations.extend(self._check_additional_properties(entity, schema))
        return violations

    # -- obrigatoriedade -----------------------------------------------

    def _check_required(self, entity: dict[str, Any], schema: dict[str, Any]) -> list[Violation]:
        violations: list[Violation] = []
        required = list(schema.get("required", []))
        any_of = schema.get("anyOf", [])

        conditional_fields: set[str] = set()
        conditional_satisfied = False
        for clause in any_of:
            clause_required = clause.get("required", [])
            conditional_fields.update(clause_required)
            if clause_required and all(
                field in entity and entity[field] is not None for field in clause_required
            ):
                conditional_satisfied = True

        for field in required:
            if field in conditional_fields:
                continue
            if field not in entity or entity[field] is None:
                violations.append(self._missing_violation(field))

        if any_of and not conditional_satisfied:
            primary_clause_fields = any_of[0].get("required", [])
            for field in primary_clause_fields:
                if field not in entity or entity[field] is None:
                    violations.append(self._missing_violation(field))

        return violations

    @staticmethod
    def _missing_violation(field: str) -> Violation:
        return Violation(
            attribute_path=field,
            severity=ViolationSeverity.ERROR,
            rule="required_property_missing",
            expected="present",
            found="absent",
            message=f"Propriedade obrigatoria '{field}' esta ausente.",
            detected_by=DetectionSource.STRUCTURAL,
        )

    # -- tipo / formato / faixa / enum, por propriedade declarada -------

    def _check_properties(self, entity: dict[str, Any], schema: dict[str, Any]) -> list[Violation]:
        violations: list[Violation] = []
        properties: dict[str, Any] = schema.get("properties", {})
        for name, prop_schema in properties.items():
            if name in _ENVELOPE_FIELDS or name not in entity or entity[name] is None:
                continue
            value = entity[name]
            violations.extend(self._check_type(name, value, prop_schema))
            violations.extend(self._check_format(name, value, prop_schema))
            violations.extend(self._check_range(name, value, prop_schema))
            violations.extend(self._check_enum(name, value, prop_schema))
        return violations

    def _check_type(self, name: str, value: Any, prop_schema: dict[str, Any]) -> list[Violation]:
        expected_type = prop_schema.get("type")
        if expected_type not in _JSON_TYPE_PYTHON:
            return []
        if expected_type == "number" and isinstance(value, bool):
            is_valid = False
        else:
            is_valid = isinstance(value, _JSON_TYPE_PYTHON[expected_type])
        if is_valid:
            return []
        return [
            Violation(
                attribute_path=name,
                severity=ViolationSeverity.ERROR,
                rule="type_mismatch",
                expected=expected_type,
                found=self._json_type_name(value),
                message=(
                    f"Atributo '{name}' esperava tipo '{expected_type}', "
                    f"encontrado '{self._json_type_name(value)}'."
                ),
                detected_by=DetectionSource.STRUCTURAL,
            )
        ]

    def _check_format(self, name: str, value: Any, prop_schema: dict[str, Any]) -> list[Violation]:
        if prop_schema.get("format") != "date-time":
            return []
        if isinstance(value, str) and self._is_valid_datetime(value):
            return []
        return [
            Violation(
                attribute_path=name,
                severity=ViolationSeverity.ERROR,
                rule="format_invalid",
                expected="date-time",
                found=value if isinstance(value, str) else self._json_type_name(value),
                message=f"Atributo '{name}' nao e um date-time ISO 8601 valido.",
                detected_by=DetectionSource.STRUCTURAL,
            )
        ]

    @staticmethod
    def _is_valid_datetime(value: str) -> bool:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return True
        except ValueError:
            return False

    def _check_range(self, name: str, value: Any, prop_schema: dict[str, Any]) -> list[Violation]:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return []
        minimum = prop_schema.get("minimum")
        maximum = prop_schema.get("maximum")
        out_of_range = (minimum is not None and value < minimum) or (
            maximum is not None and value > maximum
        )
        if not out_of_range:
            return []
        bounds = f"[{minimum if minimum is not None else '-inf'}, {maximum if maximum is not None else '+inf'}]"
        return [
            Violation(
                attribute_path=name,
                severity=ViolationSeverity.ERROR,
                rule="value_out_of_range",
                expected=bounds,
                found=str(value),
                message=f"Atributo '{name}' com valor {value} fora da faixa permitida {bounds}.",
                detected_by=DetectionSource.STRUCTURAL,
            )
        ]

    def _check_enum(self, name: str, value: Any, prop_schema: dict[str, Any]) -> list[Violation]:
        allowed = prop_schema.get("enum")
        if allowed is None or value in allowed:
            return []
        return [
            Violation(
                attribute_path=name,
                severity=ViolationSeverity.ERROR,
                rule="enum_violation",
                expected=", ".join(str(item) for item in allowed),
                found=str(value),
                message=f"Atributo '{name}' com valor '{value}' fora dos valores permitidos.",
                detected_by=DetectionSource.STRUCTURAL,
            )
        ]

    # -- additionalProperties --------------------------------------------

    def _check_additional_properties(
        self, entity: dict[str, Any], schema: dict[str, Any]
    ) -> list[Violation]:
        if schema.get("additionalProperties", True) is not False:
            return []
        known = set(schema.get("properties", {}).keys()) | _ENVELOPE_FIELDS
        violations = []
        for name in entity:
            if name in known:
                continue
            violations.append(
                Violation(
                    attribute_path=name,
                    severity=ViolationSeverity.WARNING,
                    rule="unexpected_property",
                    expected=None,
                    found=name,
                    message=f"Atributo '{name}' nao esta declarado no schema.",
                    detected_by=DetectionSource.STRUCTURAL,
                )
            )
        return violations

    @staticmethod
    def _json_type_name(value: Any) -> str:
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, (int, float)):
            return "number"
        if isinstance(value, str):
            return "string"
        if isinstance(value, dict):
            return "object"
        if isinstance(value, list):
            return "array"
        return type(value).__name__
