"""Tabelas SQLAlchemy Core para o agregado AuditRun. Ver
.cursor/specs/fase3.spec.md e docs/plano_refatoracao_v3.md, Parte III, 3.7.

NOTA: assim como schema_cache (Fase 2), estas tabelas sao criadas aqui via
`metadata.create_all()` (`create_all()` abaixo) — nao ainda por uma migration
Alembic aplicada de fato (essa parte eu escrevi mas nao consegui executar
neste ambiente, ver migrations/versions/ e o aviso no relatorio da Fase 3).

Desvio deliberado do esboco SQL do plano geral (Parte III, 3.7): NAO ha uma
tabela `tenants` separada. O dominio (Fase 1) modela Tenant como um value
object (fiware_service + fiware_service_path) sem identidade propria nem
CRUD — nenhum teste de nenhuma fase pede gerenciar Tenant como entidade. Os
dois campos ficam denormalizados direto em `audit_runs`.
"""

from __future__ import annotations

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncEngine

metadata = MetaData()

audit_runs_table = Table(
    "audit_runs",
    metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True),
    Column("tenant_fiware_service", String, nullable=False),
    Column("tenant_fiware_service_path", String, nullable=False),
    Column("entity_type", String, nullable=True),
    Column("status", String, nullable=False),
    Column("total_entities", Integer, nullable=False, default=0),
    Column("conformant_count", Integer, nullable=False, default=0),
    Column("non_conformant_count", Integer, nullable=False, default=0),
    Column("partial_count", Integer, nullable=False, default=0),
    Column("no_model_count", Integer, nullable=False, default=0),
    Column("schema_unavailable_count", Integer, nullable=False, default=0),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("broker_url", String, nullable=False),
    # Fase 5 (progresso/worker, .cursor/specs/fase5.spec.md secoes 3.1/4):
    # total_entities_discovered fica NULL ate' fetch_entities() retornar
    # (nunca 0 inventado); failure_reason so' e' preenchido quando
    # status=FAILED.
    Column("total_entities_discovered", Integer, nullable=True),
    Column("failure_reason", String, nullable=True),
    Index(
        "ix_audit_runs_tenant_started_at",
        "tenant_fiware_service",
        "tenant_fiware_service_path",
        "started_at",
    ),
)

entity_reports_table = Table(
    "entity_reports",
    metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True),
    Column("run_id", PG_UUID(as_uuid=True), ForeignKey("audit_runs.id"), nullable=False),
    Column("entity_id", String, nullable=False),
    Column("entity_type", String, nullable=False),
    Column("data_model_subject", String, nullable=True),
    Column("data_model_name", String, nullable=True),
    Column("data_model_version", String, nullable=True),
    Column("data_model_schema_url", String, nullable=True),
    Column("status", String, nullable=False),
    Column("schema_origin_source", String, nullable=True),
    Column("schema_origin_fetched_at", DateTime(timezone=True), nullable=True),
    Column("semantic_analysis_skipped", Boolean, nullable=False),
    Column("analyzed_at", DateTime(timezone=True), nullable=False),
    # Fase 10 (.cursor/specs/fase10.spec.md, secao 2/3.3/3.4): todas
    # nullable de proposito, mesmo padrao de total_entities_discovered
    # (migration 42889f2ad3cf) — None sempre que a medicao nao se aplica
    # (relatorio anterior a esta migration, ou Nivel 2 nao rodou), nunca um
    # 0 inventado que seria indistinguivel de "mediu zero".
    Column("processing_duration_seconds", Float, nullable=True),
    Column("semantic_analysis_backend", String, nullable=True),
    Column("semantic_analysis_compute_seconds", Float, nullable=True),
    Column("semantic_analysis_prompt_tokens", Integer, nullable=True),
    Column("semantic_analysis_completion_tokens", Integer, nullable=True),
    UniqueConstraint("run_id", "entity_id", name="uq_entity_reports_run_entity"),
    Index("ix_entity_reports_run_status", "run_id", "status"),
)

violations_table = Table(
    "violations",
    metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True),
    Column("report_id", PG_UUID(as_uuid=True), ForeignKey("entity_reports.id"), nullable=False),
    Column("attribute_path", String, nullable=False),
    Column("severity", String, nullable=False),
    Column("rule", String, nullable=False),
    Column("expected", String, nullable=True),
    Column("found", String, nullable=True),
    Column("message", String, nullable=False),
    Column("detected_by", String, nullable=False),
)

recommendations_table = Table(
    "recommendations",
    metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True),
    Column("report_id", PG_UUID(as_uuid=True), ForeignKey("entity_reports.id"), nullable=False),
    Column("attribute_path", String, nullable=False),
    Column("action", String, nullable=False),
    Column("proposed_patch", JSONB, nullable=False),
    Column("rationale", String, nullable=False),
    Column("confidence", Float, nullable=False),
    Column("applied", Boolean, nullable=False, default=False),
)


knowledge_chunks_table = Table(
    # Fase 6 (RAG, .cursor/specs/fase6.spec.md, secao 5). `chunk_id` (nao
    # um uuid gerado) e' a chave primaria de proposito: e' o que torna o
    # upsert da ingestao (SyncKnowledgeBaseUseCase) uma unica operacao por
    # id de origem do corpus curado, sem precisar de tabela de mapeamento
    # auxiliar. Extensao `vector` ja criada na migration inicial (Fase 3),
    # reservada explicitamente para esta fase.
    "knowledge_chunks",
    metadata,
    Column("chunk_id", String, primary_key=True),
    Column("category", String, nullable=False),
    Column("content", String, nullable=False),
    Column("tags", JSONB, nullable=False, server_default="[]"),
    Column("embedding", Vector(384), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

Index(
    "ix_knowledge_chunks_embedding_cosine",
    knowledge_chunks_table.c.embedding,
    postgresql_using="hnsw",
    postgresql_ops={"embedding": "vector_cosine_ops"},
)


async def create_all(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        # Fase 6: knowledge_chunks.embedding e' `vector(384)` — a
        # extensao precisa existir antes do create_all() criar a
        # tabela (mesmo comando que a migration inicial roda, secao
        # 5 do spec da Fase 6). create_all() e' usado so' pelos
        # testes de integracao (nunca em producao, que usa Alembic).
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(metadata.create_all)
