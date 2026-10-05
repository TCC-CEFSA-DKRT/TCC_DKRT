"""add tenant_accounts table (ADR-0019, secao 1)

Revision ID: edfd0898f739
Revises: 92150912594b
Create Date: 2026-09-26

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "edfd0898f739"
down_revision: Union[str, None] = "92150912594b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_accounts",
        sa.Column("fiware_service", sa.String(), nullable=False),
        sa.Column("fiware_service_path", sa.String(), nullable=False),
        sa.Column("broker_url", sa.String(), nullable=False),
        sa.Column("broker_api_key", sa.String(), nullable=True),
        sa.Column("login_email", sa.String(), nullable=True),
        sa.Column("password_hash", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint(
            "fiware_service", "fiware_service_path", name="pk_tenant_accounts"
        ),
        sa.UniqueConstraint("login_email", name="uq_tenant_accounts_login_email"),
        sa.CheckConstraint(
            "(login_email IS NULL) = (password_hash IS NULL)",
            name="ck_tenant_accounts_login_pair",
        ),
        sa.CheckConstraint("broker_url <> ''", name="ck_tenant_accounts_broker_url_not_empty"),
    )


def downgrade() -> None:
    op.drop_table("tenant_accounts")
