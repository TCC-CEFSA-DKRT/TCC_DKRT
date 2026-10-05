"""add entity_reports measurement columns (Fase 10 — tempo e custo por entidade)

Ver .cursor/specs/fase10.spec.md, secoes 2, 3.3 e 3.4. Migration aditiva
(nao mexe na tabela inicial, 2f62abb9e945) — relatorios ja podem existir em
entity_reports quando esta migration roda; as cinco colunas nascem
nullable de proposito, mesmo padrao de total_entities_discovered
(42889f2ad3cf): None sempre que a medicao nao se aplica (relatorio anterior
a esta migration, ou Nivel 2 nao rodou), nunca um 0 inventado que seria
indistinguivel de "mediu zero".

`processing_duration_seconds` cobre a metrica 3.3 (tempo por entidade,
Niveis 1+2 juntos). As quatro colunas `semantic_analysis_*` cobrem a
metrica 3.4 (custo de inferencia do Nivel 2): backend usado
(ollama/bedrock) e, dependendo do backend, tempo de computo (Ollama,
`total_duration` do /api/generate) ou tokens de prompt/completion
(Bedrock, `usage.input_tokens`/`output_tokens` da API de mensagens da
Anthropic) — nunca as duas coisas ao mesmo tempo, por isso todas ficam
separadas e nullable em vez de uma unica coluna "cost".

Revision ID: 92150912594b
Revises: d04e459a57d1
Create Date: 2026-09-14

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "92150912594b"
down_revision: Union[str, None] = "d04e459a57d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "entity_reports", sa.Column("processing_duration_seconds", sa.Float(), nullable=True)
    )
    op.add_column(
        "entity_reports", sa.Column("semantic_analysis_backend", sa.String(), nullable=True)
    )
    op.add_column(
        "entity_reports",
        sa.Column("semantic_analysis_compute_seconds", sa.Float(), nullable=True),
    )
    op.add_column(
        "entity_reports",
        sa.Column("semantic_analysis_prompt_tokens", sa.Integer(), nullable=True),
    )
    op.add_column(
        "entity_reports",
        sa.Column("semantic_analysis_completion_tokens", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("entity_reports", "semantic_analysis_completion_tokens")
    op.drop_column("entity_reports", "semantic_analysis_prompt_tokens")
    op.drop_column("entity_reports", "semantic_analysis_compute_seconds")
    op.drop_column("entity_reports", "semantic_analysis_backend")
    op.drop_column("entity_reports", "processing_duration_seconds")
