"""Create Alembic version tracking for infrastructure baseline.

Revision ID: 20260723_01
Revises:
Create Date: 2026-07-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260723_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """The baseline intentionally adds no business tables."""
    op.execute("SELECT 1")


def downgrade() -> None:
    """No schema objects are owned by the baseline."""
