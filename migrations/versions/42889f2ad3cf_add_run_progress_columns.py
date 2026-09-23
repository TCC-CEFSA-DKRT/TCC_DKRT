"""add total_entities_discovered and failure_reason to audit_runs

Ver .cursor/specs/fase5.spec.md, secoes 3.1 e 4. Migration aditiva (nao
mexe na inicial, 2f62abb9e945) — dado real ja pode existir em audit_runs
quando esta migration roda; as duas colunas nascem nullable de proposito,
entao nenhuma linha existente precisa de backfill.

Revision ID: 42889f2ad3cf
Revises: 2f62abb9e945
Create Date: 2026-09-06

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "42889f2ad3cf"
down_revision: Union[str, None] = "2f62abb9e945"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("audit_runs", sa.Column("total_entities_discovered", sa.Integer(), nullable=True))
    op.add_column("audit_runs", sa.Column("failure_reason", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("audit_runs", "failure_reason")
    op.drop_column("audit_runs", "total_entities_discovered")
