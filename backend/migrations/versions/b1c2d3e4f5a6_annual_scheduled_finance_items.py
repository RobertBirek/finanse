"""Allow annual PLN scheduled finance items."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "a6b7c8d9e0f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("scheduled_finance_items", sa.Column("due_month", sa.Integer(), nullable=True))
    op.drop_constraint(
        "ck_scheduled_finance_item_cadence", "scheduled_finance_items", type_="check"
    )
    op.create_check_constraint(
        "ck_scheduled_finance_item_cadence",
        "scheduled_finance_items",
        "cadence IN ('monthly', 'annual')",
    )
    op.create_check_constraint(
        "ck_scheduled_finance_item_due_month",
        "scheduled_finance_items",
        "(cadence = 'monthly' AND due_month IS NULL) "
        "OR (cadence = 'annual' AND due_month BETWEEN 1 AND 12)",
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE scheduled_finance_items IN ACCESS EXCLUSIVE MODE"))
    if connection.scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM scheduled_finance_items WHERE cadence = 'annual')")
    ):
        raise RuntimeError("Cannot downgrade while annual scheduled items exist")
    op.drop_constraint(
        "ck_scheduled_finance_item_due_month", "scheduled_finance_items", type_="check"
    )
    op.drop_constraint(
        "ck_scheduled_finance_item_cadence", "scheduled_finance_items", type_="check"
    )
    op.create_check_constraint(
        "ck_scheduled_finance_item_cadence",
        "scheduled_finance_items",
        "cadence = 'monthly'",
    )
    op.drop_column("scheduled_finance_items", "due_month")
