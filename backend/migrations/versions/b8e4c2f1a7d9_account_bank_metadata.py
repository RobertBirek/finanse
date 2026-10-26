"""add nullable account bank metadata

Revision ID: b8e4c2f1a7d9
Revises: c7f8c620460d
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8e4c2f1a7d9"
down_revision: str | None = "c7f8c620460d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("bank_name", sa.String(length=200), nullable=True))
    op.add_column("accounts", sa.Column("account_holder", sa.String(length=200), nullable=True))
    op.add_column("accounts", sa.Column("iban", sa.String(length=34), nullable=True))
    op.add_column("accounts", sa.Column("bic", sa.String(length=11), nullable=True))
    op.add_column("accounts", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("accounts", "notes")
    op.drop_column("accounts", "bic")
    op.drop_column("accounts", "iban")
    op.drop_column("accounts", "account_holder")
    op.drop_column("accounts", "bank_name")
