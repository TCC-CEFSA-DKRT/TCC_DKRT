"""Container — composition root. Ver docs/plano_refatoracao_v3.md, Parte
III, 2.2 (infrastructure/config/container.py).

Unico lugar do projeto que instancia adapters concretos e os injeta atras
dos ports — API REST, worker e CLI dependem so' deste modulo, nunca de uma
classe de infrastructure diretamente. `UnitOfWork` e' criado por chamada
(nunca reutilizado entre requests) porque cada `async with uow:` abre sua
propria conexao/transacao (Fase 3) — compartilhar a instancia entre
requisicoes concorrentes misturaria transacoes de auditorias diferentes.
"""

from __future__ import annotations

from functools import lru_cache

from http.cookiejar import CookieJar, DefaultCookiePolicy

import httpx
from cryptography.fernet import Fernet, MultiFernet
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from auditor.application.use_cases.interpret_audit_command import InterpretAuditCommandUseCase
from auditor.application.use_cases.run_audit import RunAuditUseCase
from auditor.application.use_cases.sync_catalog import SyncCatalogUseCase
from auditor.application.use_cases.sync_knowledge_base import SyncKnowledgeBaseUseCase
from auditor.domain.ports.context_broker_port import ContextBrokerPort
from auditor.domain.services.structural_validator import StructuralValidator
from auditor.infrastructure.config.settings import Settings
from auditor.infrastructure.context_broker.ngsi_v2_mapper import NgsiV2Mapper
from auditor.infrastructure.context_broker.orion_adapter import OrionAdapter
from auditor.infrastructure.context_broker.self_hosted_context_broker import (
    SelfHostedContextBroker,
)
from auditor.infrastructure.context_broker.tenant_routed_context_broker import (
    TenantRoutedContextBroker,
)
from auditor.infrastructure.persistence.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
from auditor.domain.ports.job_queue_port import JobQueuePort
from auditor.infrastructure.queue.local_job_queue import LocalJobQueue
from auditor.infrastructure.queue.sqs_job_queue import SqsJobQueue
from auditor.infrastructure.llm.ollama_analyzer import OllamaAnalyzer
from auditor.infrastructure.llm.ollama_command_interpreter import OllamaCommandInterpreter
from auditor.infrastructure.rag.corpus_loader import CorpusLoader
from auditor.infrastructure.rag.embedder import Embedder, SentenceTransformersEmbedder
from auditor.infrastructure.schema_catalog.catalog_sync_status_repository import (
    CatalogSyncStatusRepository,
)
from auditor.infrastructure.rag.pgvector_retriever import PgVectorRetriever
from auditor.infrastructure.schema_catalog.catalog_index import CatalogIndex
from auditor.infrastructure.schema_catalog.conditional_fetcher import ConditionalSchemaFetcher
from auditor.infrastructure.schema_catalog.in_memory_cache import InMemorySchemaCache
from auditor.infrastructure.schema_catalog.postgres_schema_cache_repository import (
    PostgresSchemaCacheRepository,
)
from auditor.infrastructure.schema_catalog.smart_data_models_adapter import SmartDataModelsAdapter
from auditor.infrastructure.persistence.tenant_account_repository import TenantAccountRepository


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url, hide_parameters=True)


@lru_cache
def get_http_client() -> httpx.AsyncClient:
    # Um unico cliente HTTP compartilhado (pool de conexoes) para todo o
    # processo — reaberto a cada request seria caro e desperdicaria
    # keep-alive; httpx.AsyncClient e' seguro para uso concorrente.
    return httpx.AsyncClient()


@lru_cache
def get_catalog_sync_status_repository() -> CatalogSyncStatusRepository:
    return CatalogSyncStatusRepository(get_engine())


@lru_cache
def get_tenant_account_repository() -> TenantAccountRepository:
    keys = get_settings().broker_api_key_encryption_keys_list
    if not keys:
        raise RuntimeError("BROKER_API_KEY_ENCRYPTION_KEYS nao configurada")
    return TenantAccountRepository(
        get_engine(),
        MultiFernet([Fernet(key) for key in keys]),
        require_https=get_settings().deployment_mode == "saas",
    )


@lru_cache
def get_catalog_index() -> CatalogIndex:
    # Extraido de dentro de get_schema_catalog() para tambem poder ser
    # injetado em get_sync_catalog_use_case() (linha abaixo) -- mesma
    # instancia dos dois lugares (CatalogIndex e' stateless o bastante
    # para isso ser so' uma questao de nao instanciar duas vezes a toa,
    # nao uma questao de correcao).
    return CatalogIndex()


@lru_cache
def get_schema_catalog() -> SmartDataModelsAdapter:
    return SmartDataModelsAdapter(
        catalog_index=get_catalog_index(),
        memory_cache=InMemorySchemaCache(),
        cache_repository=PostgresSchemaCacheRepository(get_engine()),
        fetcher=ConditionalSchemaFetcher(get_http_client()),
    )


@lru_cache
def get_broker_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        cookies=CookieJar(policy=DefaultCookiePolicy(allowed_domains=[])),
        follow_redirects=False,
    )


def get_context_broker() -> ContextBrokerPort:
    settings = get_settings()
    if settings.deployment_mode == "saas":
        return TenantRoutedContextBroker(
            get_tenant_account_repository(), client=get_broker_http_client()
        )
    if not settings.broker_api_key_encryption_keys_list:
        return OrionAdapter(settings.fiware_broker_url, client=get_http_client())
    return SelfHostedContextBroker(
        get_tenant_account_repository(),
        client=get_http_client(),
        default_broker_url=settings.fiware_broker_url,
    )


def get_selfhosted_accounts() -> TenantAccountRepository | None:
    return get_tenant_account_repository() if get_settings().broker_api_key_encryption_keys_list else None


def get_unit_of_work() -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(get_engine())


@lru_cache
def get_job_queue() -> JobQueuePort:
    # Fase 5 (.cursor/specs/fase5.spec.md, secao 2.2): fila local em
    # memoria para desenvolvimento — @lru_cache de proposito, ao contrario
    # de get_unit_of_work/get_context_broker: a API (que enfileira em
    # POST /audits) e o AuditWorker (que consome, ver
    # interfaces/rest/app.py) precisam compartilhar EXATAMENTE a mesma
    # instancia dentro do mesmo processo, ja' que LocalJobQueue guarda
    # tudo em memoria (asyncio.Queue) — nao ha' nenhum broker externo por
    # tras.
    #
    # ADR-0017 corrige um gap real: esta factory retornava sempre
    # LocalJobQueue(), mesmo em producao com QUEUE_BACKEND=sqs/
    # SQS_QUEUE_URL ja' escritos no ambiente pelo user_data do EC2 desde a
    # Fase 9 — nenhum AuditJob criado por RunAuditUseCase.start() chegava
    # de fato a' fila SQS real; o Worker (EC2 ou Lambda) nunca teria algo
    # para consumir. Agora troca de fato conforme Settings.queue_backend.
    settings = get_settings()
    if settings.queue_backend == "sqs":
        if not settings.sqs_queue_url:
            raise RuntimeError(
                "Settings.queue_backend='sqs' exige sqs_queue_url configurado "
                "(SQS_QUEUE_URL no ambiente) — ver modules/queue (Fase 9)."
            )
        import boto3

        return SqsJobQueue(
            client=boto3.client("sqs"),
            queue_url=settings.sqs_queue_url,
            dead_letter_queue_url=settings.sqs_dead_letter_queue_url,
        )
    return LocalJobQueue()


@lru_cache
def get_embedder() -> Embedder:
    # Fase 6 (.cursor/specs/fase6.spec.md, secao 4/8): so' exposto para a
    # Fase 7 consumir depois (via get_knowledge_retriever) — nenhum
    # endpoint/CLI desta fase usa isto diretamente. @lru_cache porque
    # SentenceTransformersEmbedder carrega o modelo preguicosamente e o
    # peso deve ser carregado uma unica vez por processo.
    return SentenceTransformersEmbedder()


@lru_cache
def get_knowledge_retriever() -> PgVectorRetriever:
    return PgVectorRetriever(get_engine(), get_embedder())


def get_semantic_analyzer() -> OllamaAnalyzer:
    # Fase 7 (.cursor/specs/fase7.spec.md, secao 5/7): Ollama e' o
    # adaptador de dev/producao inicial. BedrockAnalyzer
    # (infrastructure/llm/bedrock_analyzer.py) existe e implementa o mesmo
    # SemanticAnalyzerPort — trocar aqui e' o unico lugar que muda quando a
    # Fase 9 decidir qual roda em producao (orcamento do AWS Academy em
    # maos). NAO tem @lru_cache: usa o mesmo get_http_client() compartilhado,
    # entao nao ha' estado proprio para reter entre chamadas.
    settings = get_settings()
    return OllamaAnalyzer(
        client=get_http_client(),
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
    )


def get_command_interpreter() -> OllamaCommandInterpreter:
    # Fase 8 (.cursor/specs/fase8.spec.md, secao 0.3): mesmo servidor
    # Ollama do get_semantic_analyzer(), prompt/adaptador proprios
    # (interpretacao de comando, nao diagnostico de entidade).
    settings = get_settings()
    return OllamaCommandInterpreter(
        client=get_http_client(),
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
    )


def get_interpret_audit_command_use_case() -> InterpretAuditCommandUseCase:
    return InterpretAuditCommandUseCase(interpreter=get_command_interpreter())


def get_run_audit_use_case() -> RunAuditUseCase:
    return RunAuditUseCase(
        context_broker=get_context_broker(),
        schema_catalog=get_schema_catalog(),
        validator=StructuralValidator(),
        mapper=NgsiV2Mapper(),
        uow=get_unit_of_work(),
        job_queue=get_job_queue(),
        knowledge_retriever=get_knowledge_retriever(),
        semantic_analyzer=get_semantic_analyzer(),
    )


def get_sync_catalog_use_case() -> SyncCatalogUseCase:
    # Fase 8 (SyncCatalogUseCase) permanece administrativo por design (ver
    # docstring do proprio use case) -- nenhum endpoint HTTP novo aqui.
    # O gatilho e' o comando `audit catalog sync` (interfaces/cli/main.py),
    # unico jeito de popular o que `GET /catalog` mostra ate' este ponto
    # (nao havia NENHUM disparo alem dos testes unitarios -- gap real
    # encontrado ao investigar por que a tela Catalog do frontend sempre
    # mostrava "nunca sincronizado").
    return SyncCatalogUseCase(
        catalog_index=get_catalog_index(),
        status_repository=get_catalog_sync_status_repository(),
    )


@lru_cache
def get_corpus_loader() -> CorpusLoader:
    return CorpusLoader()


def get_sync_knowledge_base_use_case() -> SyncKnowledgeBaseUseCase:
    # Fase 6 (fase6.spec.md, secao 8) nao exigia CLI nesta fase -- mas sem
    # NENHUM gatilho fora dos testes de integracao (testcontainers),
    # knowledge_chunks nunca e' populada de verdade e
    # PgVectorRetriever.retrieve() sempre volta vazio em producao. Mesmo
    # gap ja corrigido para o catalogo (get_sync_catalog_use_case, acima);
    # fechado agora que knowledge/*.yaml tem conteudo curado real (nao mais
    # placeholder) nas quatro categorias -- ver `audit knowledge sync` em
    # interfaces/cli/main.py.
    return SyncKnowledgeBaseUseCase(
        corpus_loader=get_corpus_loader(),
        embedder=get_embedder(),
        engine=get_engine(),
    )
