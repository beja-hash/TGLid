"""Add encrypted Telegram account storage.

Revision ID: 20260724_03
Revises: 20260723_02
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260724_03"
down_revision = "20260723_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    status = postgresql.ENUM(
        "NOT_CONFIGURED",
        "DISCONNECTED",
        "CONNECTING",
        "CONNECTED",
        "ERROR",
        name="telegram_account_status",
        create_type=False,
    )
    status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "telegram_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger()),
        sa.Column("phone_masked", sa.String(length=32)),
        sa.Column("username", sa.String(length=255)),
        sa.Column("first_name", sa.String(length=255)),
        sa.Column("last_name", sa.String(length=255)),
        sa.Column(
            "status",
            status,
            nullable=False,
            server_default=sa.text("'NOT_CONFIGURED'"),
        ),
        sa.Column("encrypted_session", sa.LargeBinary()),
        sa.Column("session_nonce", sa.LargeBinary(length=12)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("connected_at", sa.DateTime(timezone=True)),
        sa.Column("disconnected_at", sa.DateTime(timezone=True)),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(length=100)),
        sa.Column("last_error_message", sa.String(length=500)),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ux_telegram_accounts_one_active",
        "telegram_accounts",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index("ux_telegram_accounts_one_active", table_name="telegram_accounts")
    op.drop_table("telegram_accounts")
    postgresql.ENUM(name="telegram_account_status").drop(op.get_bind(), checkfirst=True)
