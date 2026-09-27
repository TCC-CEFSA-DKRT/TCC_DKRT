"""rename tenant_accounts.broker_api_key to broker_api_key_encrypted (ADR-0019)

Revision ID: 5c1f3a8e2b7d
Revises: edfd0898f739
Create Date: 2026-09-26

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "5c1f3a8e2b7d"
down_revision: Union[str, None] = "edfd0898f739"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("tenant_accounts", "broker_api_key", new_column_name="broker_api_key_encrypted")


def downgrade() -> None:
    op.alter_column("tenant_accounts", "broker_api_key_encrypted", new_column_name="broker_api_key")
