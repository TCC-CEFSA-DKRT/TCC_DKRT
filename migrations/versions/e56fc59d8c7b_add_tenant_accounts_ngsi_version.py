"""add tenant_accounts.ngsi_version (ADR-0023 -- escolher NGSI-v2 ou NGSI-LD por broker)

Revision ID: e56fc59d8c7b
Revises: 5c1f3a8e2b7d
Create Date: 2026-11-20

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e56fc59d8c7b"
down_revision: Union[str, None] = "5c1f3a8e2b7d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenant_accounts",
        sa.Column("ngsi_version", sa.String(), nullable=False, server_default="v2"),
    )


def downgrade() -> None:
    op.drop_column("tenant_accounts", "ngsi_version")
