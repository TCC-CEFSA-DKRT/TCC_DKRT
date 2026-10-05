"""NgsiV2Mapper — ver .cursor/specs/fase4.spec.md, secao 1, e
docs/plano_refatoracao_v3.md, Parte III, 3.2.

Remove exatamente UM nivel de envelope NGSI-v2 (`{"type":..., "value":...,
"metadata": {...}}` -> o valor puro). Nunca desce recursivamente dentro do
proprio valor — um GeoProperty com GeoJSON aninhado, por exemplo, permanece
intacto, porque a estrutura interna dele nao e' envelope NGSI, e' o dado em
si. `id`/`type` nao sao envelopados pelo NGSI e sao preservados como vieram.

O `RawEntity` original (nao mapeado) e' quem preserva metadados como
`timestamp` para uso futuro do Nivel 2 (Fase 7) — este mapeador serve
apenas a validacao estrutural (Nivel 1), que nao precisa de metadados.
"""

from __future__ import annotations

from typing import Any

from auditor.domain.errors import MalformedAttributeError
from auditor.domain.ports.context_broker_port import RawEntity

_ENVELOPE_FIELDS = {"id", "type"}


class NgsiV2Mapper:
    def to_plain_values(self, raw_entity: RawEntity) -> dict[str, Any]:
        plain: dict[str, Any] = {}
        for key, value in raw_entity.items():
            if key in _ENVELOPE_FIELDS:
                plain[key] = value
                continue
            if not isinstance(value, dict) or "value" not in value:
                raise MalformedAttributeError(key)
            plain[key] = value["value"]
        return plain
