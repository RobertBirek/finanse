"""pay cycle cashflow

Revision ID: 8a6d0c1e2b3f
Revises: f2c8d4e6a1b9
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8a6d0c1e2b3f"
down_revision: str | None = "f2c8d4e6a1b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "finance_settings",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("payday_day", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("payday_account_id", sa.UUID(), nullable=True),
        sa.Column("forecast_horizon_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("overdue_grace_days", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("payday_day BETWEEN 1 AND 28", name="ck_finance_settings_payday_day"),
        sa.CheckConstraint(
            "forecast_horizon_days BETWEEN 1 AND 90", name="ck_finance_settings_forecast_horizon"
        ),
        sa.CheckConstraint(
            "overdue_grace_days BETWEEN 0 AND 14", name="ck_finance_settings_overdue_grace"
        ),
        sa.ForeignKeyConstraint(["payday_account_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_finance_settings_user_id"),
    )
    op.create_table(
        "scheduled_finance_items",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("category_id", sa.UUID(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("cadence", sa.String(length=20), nullable=False, server_default="monthly"),
        sa.Column("due_day", sa.Integer(), nullable=False),
        sa.Column("amount_method", sa.String(length=20), nullable=False),
        sa.Column("fixed_amount_pln", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("type IN ('income', 'expense')", name="ck_scheduled_finance_item_type"),
        sa.CheckConstraint("cadence = 'monthly'", name="ck_scheduled_finance_item_cadence"),
        sa.CheckConstraint("due_day BETWEEN 1 AND 28", name="ck_scheduled_finance_item_due_day"),
        sa.CheckConstraint(
            "amount_method IN ('fixed', 'last_actual')",
            name="ck_scheduled_finance_item_amount_method",
        ),
        sa.CheckConstraint(
            "(amount_method = 'fixed' AND fixed_amount_pln > 0) "
            "OR (amount_method = 'last_actual' AND fixed_amount_pln IS NULL)",
            name="ck_scheduled_finance_item_amount",
        ),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_scheduled_finance_items_user_id"),
        "scheduled_finance_items",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_scheduled_finance_items_user_active",
        "scheduled_finance_items",
        ["user_id", "is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_scheduled_finance_items_user_active", table_name="scheduled_finance_items")
    op.drop_index(op.f("ix_scheduled_finance_items_user_id"), table_name="scheduled_finance_items")
    op.drop_table("scheduled_finance_items")
    op.drop_table("finance_settings")
