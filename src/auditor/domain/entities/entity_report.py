"""EntityReport entity — ver .cursor/specs/fase1.spec.md, secao 2.2."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from auditor.domain.entities.recommendation import Recommendation
from auditor.domain.entities.violation import Violation
from auditor.domain.errors import InconsistentEntityReportError
from auditor.domain.value_objects.conformance_status import ConformanceStatus
from auditor.domain.value_objects.data_model_ref import DataModelRef
from auditor.domain.value_objects.entity_type import EntityType


class SchemaSource(str, Enum):
    LIVE = "live"
    CACHE = "cache"


@dataclass(frozen=True)
class SchemaOrigin:
    """De onde veio o schema usado nesta analise — honestidade metodologica:
    um relatorio vindo de schema em cache nunca fica indistinguivel de um
    confirmado ao vivo."""

    source: SchemaSource
    fetched_at: datetime


class InferenceBackend(str, Enum):
    OLLAMA = "ollama"
    BEDROCK = "bedrock"


@dataclass(frozen=True)
class SemanticAnalysisUsage:
    """Uso de inferencia do Nivel 2 nesta entidade — ver
    .cursor/specs/fase10.spec.md, secao 3.4 (custo de inferencia). Os
    campos disponiveis dependem do backend: Ollama local nao tem billing
    por token (so' `compute_seconds`, via `total_duration` da resposta);
    Bedrock nao expoe tempo de computo diretamente, so' tokens de
    prompt/completion. Nunca os dois preenchidos ao mesmo tempo — cada
    None significa "esse backend nao mede isso", nunca "mediu zero"."""

    backend: InferenceBackend
    compute_seconds: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass
class EntityReport:
    """Resultado de conformidade de uma unica entidade dentro de um AuditRun."""

    entity_id: str
    entity_type: EntityType
    data_model: DataModelRef | None
    status: ConformanceStatus
    violations: list[Violation]
    recommendations: list[Recommendation] = field(default_factory=list)
    schema_origin: SchemaOrigin | None = None
    semantic_analysis_skipped: bool = True
    analyzed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Fase 10 (.cursor/specs/fase10.spec.md, secao 3.3/3.4): nullable de
    # proposito — None em relatorios anteriores a esta instrumentacao, ou
    # quando o Nivel 2 nao rodou (semantic_analysis_usage).
    processing_duration_seconds: float | None = None
    semantic_analysis_usage: SemanticAnalysisUsage | None = None

    def __post_init__(self) -> None:
        if self.data_model is None and self.status != ConformanceStatus.NO_MODEL_FOUND:
            raise InconsistentEntityReportError(
                "EntityReport.data_model e None mas status nao e NO_MODEL_FOUND."
            )
        if self.data_model is not None and self.status == ConformanceStatus.NO_MODEL_FOUND:
            raise InconsistentEntityReportError(
                "EntityReport.status e NO_MODEL_FOUND mas data_model esta presente."
            )
        # NO_MODEL_FOUND e SCHEMA_UNAVAILABLE (ajuste retroativo da Fase 2,
        # .cursor/specs/fase2.spec.md secao 4) nunca sao derivados de
        # violacoes — os dois so fazem sentido quando o Nivel 1 nem chegou a
        # rodar (sem schema, nao ha o que validar).
        if self.status in (ConformanceStatus.NO_MODEL_FOUND, ConformanceStatus.SCHEMA_UNAVAILABLE):
            return
        expected_status = ConformanceStatus.derive(self.violations, model_found=True)
        if expected_status != self.status:
            raise InconsistentEntityReportError(
                f"EntityReport.status ({self.status}) inconsistente com suas "
                f"violacoes (derivacao indica {expected_status})."
            )
