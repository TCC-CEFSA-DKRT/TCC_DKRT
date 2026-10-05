"""add knowledge_chunks table (Fase 6 — RAG)

Ver .cursor/specs/fase6.spec.md, secao 5. Migration aditiva sobre a
extensao `vector`, ja criada e habilitada na migration inicial
(2f62abb9e945) especificamente reservada para esta fase. `chunk_id` (nao
um uuid gerado) e' a chave primaria: e' o campo `id` de origem de cada
entrada curada em knowledge/*.yaml, o que torna o upsert da ingestao
(SyncKnowledgeBaseUseCase, Fase 6 secao 7) uma unica operacao por
`chunk_id`, sem tabela de mapeamento auxiliar. Indice HNSW por distancia
de cosseno (pgvector >= 0.5.0) para a busca de similaridade do
PgVectorRetriever.

Revision ID: 0cfa66a23db8
Revises: 42889f2ad3cf
Create Date: 2026-09-06

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0cfa66a23db8"
down_revision: Union[str, None] = "42889f2ad3cf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_chunks",
        sa.Column("chunk_id", sa.String(), primary_key=True),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("tags", JSONB(), nullable=False, server_default="[]"),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_embedding_cosine ON knowledge_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_embedding_cosine", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
