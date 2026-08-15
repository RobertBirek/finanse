"""category budgets

Revision ID: 4340d1460982
Revises: 8a6d0c1e2b3f
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4340d1460982"
down_revision: str | None = "8a6d0c1e2b3f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "category_budgets",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("category_id", sa.UUID(), nullable=False),
        sa.Column("amount_pln", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("amount_pln > 0", name="ck_category_budget_amount"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "category_id", name="uq_category_budget_user_category"),
    )
    op.create_index(
        op.f("ix_category_budgets_user_id"), "category_budgets", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_category_budgets_category_id"), "category_budgets", ["category_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_category_budgets_category_id"), table_name="category_budgets")
    op.drop_index(op.f("ix_category_budgets_user_id"), table_name="category_budgets")
    op.drop_table("category_budgets")
