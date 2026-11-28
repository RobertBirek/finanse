"""Persist conditional native-currency recurring obligations."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conditional_recurring_obligations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("condition_key", sa.String(length=100), nullable=False),
        sa.Column(
            "condition_state", sa.String(length=20), nullable=False, server_default="unknown"
        ),
        sa.Column("cadence", sa.String(length=20), nullable=False, server_default="monthly"),
        sa.Column("due_month", sa.Integer(), nullable=True),
        sa.Column("due_day", sa.Integer(), nullable=False),
        sa.Column("primary_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("primary_amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("primary_currency", sa.String(length=3), nullable=False),
        sa.Column("fallback_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fallback_amount_minor", sa.BigInteger(), nullable=True),
        sa.Column("fallback_currency", sa.String(length=3), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["primary_account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["fallback_account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "cadence IN ('monthly', 'annual')", name="ck_conditional_obligation_cadence"
        ),
        sa.CheckConstraint(
            "(cadence = 'monthly' AND due_month IS NULL) "
            "OR (cadence = 'annual' AND due_month BETWEEN 1 AND 12)",
            name="ck_conditional_obligation_due_month",
        ),
        sa.CheckConstraint("due_day BETWEEN 1 AND 28", name="ck_conditional_obligation_due_day"),
        sa.CheckConstraint(
            "condition_state IN ('unknown', 'satisfied', 'not_satisfied')",
            name="ck_conditional_obligation_condition_state",
        ),
        sa.CheckConstraint(
            "primary_currency IN ('PLN', 'EUR', 'USD') "
            "AND fallback_currency IN ('PLN', 'EUR', 'USD')",
            name="ck_conditional_obligation_currency",
        ),
        sa.CheckConstraint(
            "primary_amount_minor > 0 AND (fallback_amount_minor IS NULL OR fallback_amount_minor > 0)",
            name="ck_conditional_obligation_amount",
        ),
        sa.CheckConstraint(
            "primary_account_id <> fallback_account_id",
            name="ck_conditional_obligation_distinct_accounts",
        ),
    )
    op.create_index(
        "ix_conditional_obligation_owner_active",
        "conditional_recurring_obligations",
        ["user_id", "is_active"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text("LOCK TABLE conditional_recurring_obligations IN ACCESS EXCLUSIVE MODE")
    )
    if connection.scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM conditional_recurring_obligations)")
    ):
        raise RuntimeError("Cannot downgrade while conditional recurring obligations exist")
    op.drop_index(
        "ix_conditional_obligation_owner_active", table_name="conditional_recurring_obligations"
    )
    op.drop_table("conditional_recurring_obligations")
