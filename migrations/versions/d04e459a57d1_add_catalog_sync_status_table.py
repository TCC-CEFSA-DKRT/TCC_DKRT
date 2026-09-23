"""add catalog_sync_status table (Fase 8 — tela Catalog)

Ver .cursor/specs/fase8.spec.md, secao 7. Linha unica (singleton, id
fixo "singleton") registrando o resultado da ultima tentativa de
sincronizacao do catalogo (CatalogIndex.sync(), Fase 2) — global, nao por
tenant. `last_successful_at`/`last_success_models_count` sao preservados
por `CatalogSyncStatusRepository.record()` mesmo quando uma tentativa mais
recente falha.

Revision ID: d04e459a57d1
Revises: 0cfa66a23db8
Create Date: 2026-09-06

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d04e459a57d1"
down_revision: Union[str, None] = "0cfa66a23db8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "catalog_sync_status",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_attempt_successful", sa.Boolean(), nullable=False),
        sa.Column("last_attempt_error", sa.String(), nullable=True),
        sa.Column("last_successful_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_models_count", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("catalog_sync_status")
