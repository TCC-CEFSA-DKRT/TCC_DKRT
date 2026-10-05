"""Exceções de domínio.

Toda violação de invariante levantada em qualquer lugar sob `auditor.domain`
deve derivar de `DomainError`.
"""


class DomainError(Exception):
    """Classe base para toda violação de invariante de domínio."""


class InvalidEntityTypeError(DomainError):
    """Um `EntityType` foi construído com dados inválidos."""


class InvalidDataModelRefError(DomainError):
    """Um `DataModelRef` foi construído sem algum campo obrigatório."""


class InvalidRecommendationError(DomainError):
    """Uma `Recommendation` foi construída com dados inválidos."""


class InconsistentEntityReportError(DomainError):
    """Os campos de um `EntityReport` se contradizem entre si."""


class InvariantViolationError(DomainError):
    """Violação de invariante de agregado (`RunSummary`, `AuditRun`)."""


class AmbiguousDataModelError(DomainError):
    """Mais de um Smart Data Model corresponde ao mesmo entity_type — a
    resolucao nunca escolhe um dos dois silenciosamente (Fase 2)."""


class SchemaUnavailableError(DomainError):
    """O catalogo confirma que existe um Smart Data Model para o entity_type,
    mas nao foi possivel obter o conteudo do schema agora — nem ao vivo, nem
    em nenhuma camada de cache (Fase 2). Diferente de NO_MODEL_FOUND, que
    significa que o catalogo confirma que NAO existe modelo."""


class RunNotFoundError(DomainError):
    """append_report / update_run_status chamados para um run_id que nao
    existe (ou nao pertence ao tenant informado) — nunca cria um relatorio
    orfao, solto de um run (Fase 3)."""

class MalformedAttributeError(DomainError):
    """Um atributo NGSI-v2 nao segue o envelope esperado
    (`{"type":..., "value":...}`) — ex.: falta a chave `value` (Fase 4,
    `NgsiV2Mapper`). Nomeia o atributo explicitamente; nunca deixa um
    `KeyError` generico vazar e nunca faz o mapeamento perder o dado em
    silencio."""

    def __init__(self, attribute_name: str) -> None:
        self.attribute_name = attribute_name
        super().__init__(
            f"Atributo NGSI-v2 malformado: '{attribute_name}' nao tem a chave "
            f"'value' esperada no envelope."
        )


class ContextBrokerUnavailableError(DomainError):
    """O Context Broker (Orion) esta inacessivel — rede fora do ar, timeout,
    ou resposta de erro do broker (Fase 4, `OrionAdapter`). Distinto de um
    resultado valido de auditoria (`NO_MODEL_FOUND`/`SCHEMA_UNAVAILABLE`):
    isso e' falha de infraestrutura, e quem orquestra (`RunAuditUseCase`)
    decide explicitamente marcar o run como `FAILED` por causa dela."""


class TenantBrokerNotConfiguredError(DomainError):
    def __init__(self, tenant) -> None:
        self.fiware_service = tenant.fiware_service
        self.fiware_service_path = tenant.fiware_service_path
        super().__init__(
            f"Nenhuma conta cadastrada para {tenant.fiware_service}/{tenant.fiware_service_path}."
        )


class InconsistentSemanticAnalysisResultError(DomainError):
    """Um `SemanticAnalysisResult` foi construido com
    `analysis_unavailable=True` acompanhado de violations/recommendations
    nao vazios (Fase 7) — a garantia de "se a saida do modelo nao valida,
    nada dela e' usado" e' um invariante de dominio, nao so' uma
    convencao de quem chama."""
