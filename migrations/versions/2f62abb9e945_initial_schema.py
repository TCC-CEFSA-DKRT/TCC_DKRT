"""initial schema — schema_cache (Fase 2) + audit_runs/entity_reports/
violations/recommendations (Fase 3)

Ver .cursor/specs/fase3.spec.md secao 9 e docs/plano_refatoracao_v3.md,
Parte III, 3.7. Escrita a mao (nao via `alembic revision --autogenerate`)
porque este ambiente de desenvolvimento nao tem acesso de rede ao Postgres
do docker-compose do usuario — replica exatamente as definicoes de
`auditor.infrastructure.persistence.tables` e
`auditor.infrastructure.schema_catalog.postgres_schema_cache_repository`.
NAO FOI EXECUTADA/VALIDADA contra um banco real neste ambiente; validar com
`alembic upgrade head` / `alembic downgrade base` na maquina do usuario
antes de confiar nela em producao.

Revision ID: 2f62abb9e945
Revises:
Create Date: 2026-09-06

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "2f62abb9e945"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pgvector — a imagem do docker-compose (pgvector/pgvector:pg16) ja traz
    # a extensao instalada no SO; so falta habilita-la no banco. Usada pela
    # Fase 6 (RAG); nao ha coluna vector ainda nesta migration.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "schema_cache",
        sa.Column("entity_type", sa.String(), primary_key=True),
        sa.Column("data_model_name", sa.String(), nullable=False),
        sa.Column("schema_content", JSONB(), nullable=False),
        sa.Column("etag", sa.String(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "audit_runs",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_fiware_service", sa.String(), nullable=False),
        sa.Column("tenant_fiware_service_path", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("total_entities", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conformant_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("non_conformant_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("partial_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("no_model_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("schema_unavailable_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("broker_url", sa.String(), nullable=False),
    )
    op.create_index(
        "ix_audit_runs_tenant_started_at",
        "audit_runs",
        ["tenant_fiware_service", "tenant_fiware_service_path", "started_at"],
    )

    op.create_table(
        "entity_reports",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("audit_runs.id"),
            nullable=False,
        ),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("data_model_subject", sa.String(), nullable=True),
        sa.Column("data_model_name", sa.String(), nullable=True),
        sa.Column("data_model_version", sa.String(), nullable=True),
        sa.Column("data_model_schema_url", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("schema_origin_source", sa.String(), nullable=True),
        sa.Column("schema_origin_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("semantic_analysis_skipped", sa.Boolean(), nullable=False),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "entity_id", name="uq_entity_reports_run_entity"),
    )
    op.create_index(
        "ix_entity_reports_run_status", "entity_reports", ["run_id", "status"]
    )

    op.create_table(
        "violations",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "report_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("entity_reports.id"),
            nullable=False,
        ),
        sa.Column("attribute_path", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("rule", sa.String(), nullable=False),
        sa.Column("expected", sa.String(), nullable=True),
        sa.Column("found", sa.String(), nullable=True),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("detected_by", sa.String(), nullable=False),
    )

    op.create_table(
        "recommendations",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "report_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("entity_reports.id"),
            nullable=False,
        ),
        sa.Column("attribute_path", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("proposed_patch", JSONB(), nullable=False),
        sa.Column("rationale", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("applied", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_table("recommendations")
    op.drop_table("violations")
    op.drop_index("ix_entity_reports_run_status", table_name="entity_reports")
    op.drop_table("entity_reports")
    op.drop_index("ix_audit_runs_tenant_started_at", table_name="audit_runs")
    op.drop_table("audit_runs")
    op.drop_table("schema_cache")
    # Extensao pgvector deliberadamente NAO removida no downgrade: pode ser
    # usada por outros objetos criados fora desta migration (ex.: Fase 6),
    # e DROP EXTENSION e destrutivo alem do escopo desta revisao.
