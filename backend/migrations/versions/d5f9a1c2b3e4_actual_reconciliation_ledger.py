"""actual reconciliation ledger

Revision ID: d5f9a1c2b3e4
Revises: 426284effc4d
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5f9a1c2b3e4"
down_revision: str | None = "426284effc4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("is_budget_account", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "postings",
        sa.Column("is_budget_impact", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.alter_column("postings", "account_id", existing_type=sa.UUID(), nullable=True)
    op.alter_column("accounts", "is_budget_account", server_default=None)
    op.alter_column("postings", "is_budget_impact", server_default=None)


def downgrade() -> None:
    connection = op.get_bind()
    category_only_postings = connection.execute(
        sa.text("SELECT COUNT(*) FROM postings WHERE account_id IS NULL")
    ).scalar_one()
    if category_only_postings:
        raise RuntimeError("Cannot downgrade: postings without an account exist")

    op.alter_column("postings", "account_id", existing_type=sa.UUID(), nullable=False)
    op.drop_column("postings", "is_budget_impact")
    op.drop_column("accounts", "is_budget_account")
