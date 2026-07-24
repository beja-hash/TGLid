"""Add Telegram authorization progress statuses.

Revision ID: 20260724_04
Revises: 20260724_03
Create Date: 2026-07-24
"""

from alembic import op

revision = "20260724_04"
down_revision = "20260724_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE telegram_account_status ADD VALUE IF NOT EXISTS 'AUTH_CODE_REQUIRED'")
    op.execute(
        "ALTER TYPE telegram_account_status ADD VALUE IF NOT EXISTS 'AUTH_PASSWORD_REQUIRED'"
    )


def downgrade() -> None:
    # PostgreSQL enum values cannot be safely removed without rebuilding the type.
    pass
