"""Schemas Pydantic de request/response da API REST. Ver
.cursor/specs/fase4.spec.md, secao 4.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

from auditor.domain.entities.audit_run import AuditRun
from auditor.domain.entities.entity_report import EntityReport, SemanticAnalysisUsage
from auditor.domain.entities.recommendation import Recommendation
from auditor.domain.entities.violation import Violation
from auditor.domain.ports.audit_repository_port import AuditRunSummaryView, Page
from auditor.domain.ports.command_interpreter_port import AuditCommandInterpretation

T = TypeVar("T")


class LoginRequest(BaseModel):
    login_email: str
    password: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TenantResponse(BaseModel):
    fiware_service: str
    fiware_service_path: str


class SessionResponse(BaseModel):
    deployment_mode: Literal["saas", "selfhosted"]
    tenant: TenantResponse | None


class BrokerConfigRequest(BaseModel):
    broker_url: str = Field(pattern=r"^https?://\S+$")
    fiware_service: str = Field(pattern=r"^[A-Za-z0-9_]{0,50}$")
    fiware_service_path: str = Field(default="/", pattern=r"^/([A-Za-z0-9_]+(/[A-Za-z0-9_]+)*)?$")


class BrokerConfigResponse(BaseModel):
    configured: bool
    broker_url: str
    fiware_service: str
    fiware_service_path: str


class AuditCreateRequest(BaseModel):
    entity_type: str | None = None
    entity_id: str | None = None


class AuditCreateResponse(BaseModel):
    run_id: UUID
    status: str


class AuditProgressResponse(BaseModel):
    """Fase 5 (.cursor/specs/fase5.spec.md, secao 4.1). `total` e' `None`
    ate' que o worker termine de consultar o Orion — nunca um numero
    inventado (0 seria indistinguivel de uma auditoria vazia de verdade)."""

    status: str
    processed: int
    total: int | None


class ViolationResponse(BaseModel):
    attribute_path: str
    severity: str
    rule: str
    expected: str | None
    found: str | None
    message: str
    detected_by: str

    @classmethod
    def from_domain(cls, violation: Violation) -> "ViolationResponse":
        return cls(
            attribute_path=violation.attribute_path,
            severity=violation.severity.value,
            rule=violation.rule,
            expected=violation.expected,
            found=violation.found,
            message=violation.message,
            detected_by=violation.detected_by.value,
        )


class RecommendationResponse(BaseModel):
    attribute_path: str
    action: str
    proposed_patch: dict[str, Any]
    rationale: str
    confidence: float

    @classmethod
    def from_domain(cls, recommendation: Recommendation) -> "RecommendationResponse":
        return cls(
            attribute_path=recommendation.attribute_path,
            action=recommendation.action.value,
            proposed_patch=recommendation.proposed_patch,
            rationale=recommendation.rationale,
            confidence=recommendation.confidence,
        )


class SemanticAnalysisUsageResponse(BaseModel):
    """Fase 10 (.cursor/specs/fase10.spec.md, secao 3.4) — custo de
    inferencia do Nivel 2 nesta entidade. Os campos preenchidos dependem
    do backend (`compute_seconds` so' para Ollama; `prompt_tokens`/
    `completion_tokens` so' para Bedrock); usado pelo futuro
    `scripts/run_experiment.py`, que consome esta API como cliente HTTP
    externo e nao tem acesso direto ao dominio."""

    backend: str
    compute_seconds: float | None
    prompt_tokens: int | None
    completion_tokens: int | None

    @classmethod
    def from_domain(cls, usage: SemanticAnalysisUsage) -> "SemanticAnalysisUsageResponse":
        return cls(
            backend=usage.backend.value,
            compute_seconds=usage.compute_seconds,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
        )


class EntityReportResponse(BaseModel):
    entity_id: str
    entity_type: str
    status: str
    violations: list[ViolationResponse]
    recommendations: list[RecommendationResponse]
    # Fase 7 existia no dominio desde a Fase 1, mas nunca tinha sido
    # exposto na API — a tela "Report Detail" (Fase 8, secao 5) precisa
    # distinguir "Nivel 2 nao rodou" de "Nivel 2 rodou e nao achou nada".
    semantic_analysis_skipped: bool
    # Fase 10 (.cursor/specs/fase10.spec.md, secao 3.3/3.4): None em
    # relatorios anteriores a esta instrumentacao, ou quando o Nivel 2 nao
    # rodou (semantic_analysis_usage) — nunca um valor inventado.
    processing_duration_seconds: float | None
    semantic_analysis_usage: SemanticAnalysisUsageResponse | None

    @classmethod
    def from_domain(cls, report: EntityReport) -> "EntityReportResponse":
        return cls(
            entity_id=report.entity_id,
            entity_type=report.entity_type.value,
            status=report.status.value,
            violations=[ViolationResponse.from_domain(v) for v in report.violations],
            recommendations=[
                RecommendationResponse.from_domain(r) for r in report.recommendations
            ],
            semantic_analysis_skipped=report.semantic_analysis_skipped,
            processing_duration_seconds=report.processing_duration_seconds,
            semantic_analysis_usage=(
                SemanticAnalysisUsageResponse.from_domain(report.semantic_analysis_usage)
                if report.semantic_analysis_usage
                else None
            ),
        )


class RunSummaryResponse(BaseModel):
    total_entities: int
    conformant_count: int
    non_conformant_count: int
    partial_count: int
    no_model_count: int
    schema_unavailable_count: int


class AuditRunResponse(BaseModel):
    id: UUID
    status: str
    entity_type: str | None
    summary: RunSummaryResponse
    started_at: datetime
    finished_at: datetime | None
    broker_url: str
    reports: list[EntityReportResponse]

    @classmethod
    def from_domain(cls, run: AuditRun) -> "AuditRunResponse":
        return cls(
            id=run.id,
            status=run.status.value,
            entity_type=run.entity_type.value if run.entity_type else None,
            summary=RunSummaryResponse(
                total_entities=run.summary.total_entities,
                conformant_count=run.summary.conformant_count,
                non_conformant_count=run.summary.non_conformant_count,
                partial_count=run.summary.partial_count,
                no_model_count=run.summary.no_model_count,
                schema_unavailable_count=run.summary.schema_unavailable_count,
            ),
            started_at=run.started_at,
            finished_at=run.finished_at,
            broker_url=run.broker_url,
            reports=[EntityReportResponse.from_domain(r) for r in run.reports],
        )


class AuditRunSummaryResponse(BaseModel):
    """Visao leve de um AuditRun para a tela "Audit Runs" (Fase 8, secao
    0.1/4) — sem os relatorios completos (isso e' `AuditRunResponse`,
    usado por `GET /audits/{id}`)."""

    id: UUID
    entity_type: str | None
    status: str
    summary: RunSummaryResponse
    started_at: datetime
    finished_at: datetime | None
    broker_url: str
    total_entities_discovered: int | None
    failure_reason: str | None

    @classmethod
    def from_domain(cls, view: AuditRunSummaryView) -> "AuditRunSummaryResponse":
        return cls(
            id=view.id,
            entity_type=view.entity_type.value if view.entity_type else None,
            status=view.status.value,
            summary=RunSummaryResponse(
                total_entities=view.summary.total_entities,
                conformant_count=view.summary.conformant_count,
                non_conformant_count=view.summary.non_conformant_count,
                partial_count=view.summary.partial_count,
                no_model_count=view.summary.no_model_count,
                schema_unavailable_count=view.summary.schema_unavailable_count,
            ),
            started_at=view.started_at,
            finished_at=view.finished_at,
            broker_url=view.broker_url,
            total_entities_discovered=view.total_entities_discovered,
            failure_reason=view.failure_reason,
        )


class PageResponse(BaseModel, Generic[T]):
    """Espelha `auditor.domain.ports.audit_repository_port.Page` — `has_next`
    e' calculado aqui tambem (nao so' no dominio) porque e' o dado que a
    tela "Audit Runs" usa diretamente para decidir se mostra "proxima
    pagina", sem reimplementar a conta no frontend (Fase 8, secao 1)."""

    items: list[T]
    page: int
    page_size: int
    total: int
    has_next: bool

    @classmethod
    def from_domain(
        cls, page: "Page[AuditRunSummaryView]", items: list[T]
    ) -> "PageResponse[T]":
        return cls(
            items=items,
            page=page.page,
            page_size=page.page_size,
            total=page.total,
            has_next=page.has_next,
        )


class InterpretAuditRequest(BaseModel):
    command_text: str


class InterpretAuditResponse(BaseModel):
    entity_type: str | None
    entity_id: str | None
    confidence: float
    raw_command: str

    @classmethod
    def from_domain(cls, interpretation: AuditCommandInterpretation) -> "InterpretAuditResponse":
        return cls(
            entity_type=interpretation.entity_type,
            entity_id=interpretation.entity_id,
            confidence=interpretation.confidence,
            raw_command=interpretation.raw_command,
        )


class CatalogStatusResponse(BaseModel):
    """Fase 8, secao 7 — tela "Catalog". `last_synced_at`/`models_count`
    ficam `None` quando nenhuma sincronizacao bem-sucedida jamais ocorreu
    (nunca um valor inventado); `last_sync_successful=False` sinaliza uma
    tentativa recente que falhou, mesmo que uma sincronizacao anterior
    tenha tido sucesso (o catalogo local mostrado continua sendo o da
    ultima bem-sucedida — nunca dado stale disfarcado de atual)."""

    last_synced_at: datetime | None
    last_sync_successful: bool | None
    last_sync_error: str | None
    models_count: int | None


class EntityTypesResponse(BaseModel):
    """`GET /entity-types` — tipos de entidade descobertos no broker do
    tenant (ContextBrokerPort.list_entity_types), pra tela de configuracao
    popular um seletor em vez do usuario digitar o tipo as cegas.
    `broker_reachable=False` (com `types=[]`) sinaliza que o broker nao
    respondeu — nunca um erro 5xx que bloquearia a tela; quem chama sempre
    permite entrada manual do tipo, entao descoberta indisponivel nao pode
    impedir de configurar a auditoria mesmo assim."""

    types: list[str]
    broker_reachable: bool


class CatalogModelResponse(BaseModel):
    """Um item de `GET /catalog/models` -- follow-up pos-Fase 8: a tela
    Catalog so mostrava o status agregado da sincronizacao (contagem,
    data, sucesso/falha), sem lista navegavel dos modelos em si nem jeito
    de ver o conteudo de cada um. `subject` vai junto de proposito: e' o
    que desambigua um `model_name` que exista em mais de um subject (ver
    AmbiguousDataModelError em CatalogIndex.resolve()) — sem ele, o
    frontend nao teria como pedir o schema do modelo certo."""

    subject: str
    model_name: str


class CatalogModelSchemaResponse(BaseModel):
    """Conteudo do schema de um modelo especifico -- `GET
    /catalog/models/{model_name}/schema`. Reaproveita o mesmo pipeline de
    cache de 6 camadas de SmartDataModelsAdapter.fetch_schema() (Fase 2,
    ja usado pela auditoria em si) em vez de buscar de novo por conta
    propria: `source` conta se o conteudo mostrado veio ao vivo
    (raw.githubusercontent.com) ou do cache -- honestidade metodologica
    (mesmo raciocinio de SchemaOrigin, entities/entity_report.py), nunca
    disfarcando cache de "ao vivo"."""

    subject: str
    model_name: str
    version: str
    schema_url: str
    content: dict[str, Any]
    source: str
    fetched_at: datetime
