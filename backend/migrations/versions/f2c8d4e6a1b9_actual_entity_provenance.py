"""actual entity provenance

Revision ID: f2c8d4e6a1b9
Revises: e7a4b2c6d8f0
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2c8d4e6a1b9"
down_revision: str | None = "e7a4b2c6d8f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("source", sa.String(length=50), server_default="manual", nullable=False),
    )
    op.add_column(
        "categories",
        sa.Column("source", sa.String(length=50), server_default="manual", nullable=False),
    )
    op.alter_column("accounts", "source", server_default=None)
    op.alter_column("categories", "source", server_default=None)


def downgrade() -> None:
    op.drop_column("categories", "source")
    op.drop_column("accounts", "source")
