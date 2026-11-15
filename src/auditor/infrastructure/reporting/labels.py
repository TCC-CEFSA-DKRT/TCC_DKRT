from __future__ import annotations

from auditor.domain.entities.audit_run import RunStatus
from auditor.domain.entities.recommendation import RecommendationAction
from auditor.domain.entities.violation import ViolationSeverity
from auditor.domain.value_objects.conformance_status import ConformanceStatus

SEVERITY_ORDER: tuple[ViolationSeverity, ...] = (
    ViolationSeverity.ERROR,
    ViolationSeverity.WARNING,
    ViolationSeverity.INFO,
)

SEVERITY_BADGES: dict[ViolationSeverity, str] = {
    ViolationSeverity.ERROR: "ERRO",
    ViolationSeverity.WARNING: "AVISO",
    ViolationSeverity.INFO: "INFO",
}

SEVERITY_PLURALS: dict[ViolationSeverity, str] = {
    ViolationSeverity.ERROR: "Erros",
    ViolationSeverity.WARNING: "Avisos",
    ViolationSeverity.INFO: "Informações",
}

CONFORMANCE_LABELS: dict[ConformanceStatus, str] = {
    ConformanceStatus.CONFORMANT: "Conforme",
    ConformanceStatus.PARTIAL: "Parcial",
    ConformanceStatus.NON_CONFORMANT: "Não conforme",
    ConformanceStatus.NO_MODEL_FOUND: "Sem modelo",
    ConformanceStatus.SCHEMA_UNAVAILABLE: "Schema indisponível",
}

CONFORMANCE_PRINT_ORDER: tuple[ConformanceStatus, ...] = (
    ConformanceStatus.NON_CONFORMANT,
    ConformanceStatus.PARTIAL,
    ConformanceStatus.SCHEMA_UNAVAILABLE,
    ConformanceStatus.NO_MODEL_FOUND,
    ConformanceStatus.CONFORMANT,
)

RUN_STATUS_LABELS: dict[RunStatus, str] = {
    RunStatus.QUEUED: "Na fila",
    RunStatus.RUNNING: "Em execução",
    RunStatus.COMPLETED: "Concluída",
    RunStatus.FAILED: "Falhou",
    RunStatus.PARTIAL: "Parcial",
    RunStatus.NO_ENTITIES_FOUND: "Nenhuma entidade encontrada",
}

RULE_LABELS: dict[str, str] = {
    "required_property_missing": "Atributo obrigatório ausente",
    "type_mismatch": "Tipo de dado incorreto",
    "format_invalid": "Formato inválido",
    "value_out_of_range": "Valor fora do intervalo permitido",
    "enum_violation": "Valor fora da lista permitida",
    "unexpected_property": "Atributo não previsto no modelo",
    "malformed_attribute": "Atributo fora do formato NGSI-v2",
    "attribute_name_synonym": "Nome de atributo diferente do definido no modelo",
}

ACTION_LABELS: dict[RecommendationAction, str] = {
    RecommendationAction.RENAME_ATTRIBUTE: "Renomear o atributo",
    RecommendationAction.ADD_MISSING_ATTRIBUTE: "Adicionar o atributo ausente",
    RecommendationAction.FIX_TYPE: "Corrigir o tipo de dado",
    RecommendationAction.FIX_FORMAT: "Corrigir o formato",
}

