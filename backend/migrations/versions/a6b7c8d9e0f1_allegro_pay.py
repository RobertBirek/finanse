"""Add Allegro Pay schedules and links to existing ledger transactions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "a6b7c8d9e0f1"
down_revision = "5f1d54d40a2e"
branch_labels = None
depends_on = None


def identity() -> tuple[sa.Column, ...]:
    return (
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "allegro_pay_profiles",
        *identity(),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("limit_pln", sa.BigInteger()),
        sa.UniqueConstraint("account_id", name="uq_allegro_pay_account"),
        sa.UniqueConstraint("id", "user_id", name="uq_allegro_pay_profile_owner"),
        sa.ForeignKeyConstraint(
            ["account_id", "user_id"], ["accounts.id", "accounts.user_id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "limit_pln IS NULL OR limit_pln BETWEEN 1 AND 9007199254740991",
            name="ck_allegro_pay_limit",
        ),
    )
    op.create_table(
        "allegro_pay_purchases",
        *identity(),
        sa.Column("profile_id", sa.UUID(), nullable=False),
        sa.Column("transaction_id", sa.UUID(), nullable=False),
        sa.Column("request_id", sa.UUID(), nullable=False),
        sa.Column("request_payload", JSONB(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("purchase_date", sa.Date(), nullable=False),
        sa.Column("principal_pln", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("id", "user_id", name="uq_allegro_pay_purchase_owner"),
        sa.UniqueConstraint("transaction_id", name="uq_allegro_pay_purchase_transaction"),
        sa.UniqueConstraint("profile_id", "request_id", name="uq_allegro_pay_purchase_request"),
        sa.ForeignKeyConstraint(
            ["profile_id", "user_id"],
            ["allegro_pay_profiles.id", "allegro_pay_profiles.user_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id", "user_id"],
            ["financial_transactions.id", "financial_transactions.user_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "principal_pln BETWEEN 1 AND 9007199254740991", name="ck_allegro_pay_purchase_principal"
        ),
    )
    op.create_table(
        "allegro_pay_installments",
        *identity(),
        sa.Column("purchase_id", sa.UUID(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("principal_pln", sa.BigInteger(), nullable=False),
        sa.Column("interest_pln", sa.BigInteger(), nullable=False),
        sa.Column("fees_pln", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("id", "user_id", name="uq_allegro_pay_installment_owner"),
        sa.UniqueConstraint("purchase_id", "number", name="uq_allegro_pay_installment_number"),
        sa.ForeignKeyConstraint(
            ["purchase_id", "user_id"],
            ["allegro_pay_purchases.id", "allegro_pay_purchases.user_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("number > 0", name="ck_allegro_pay_installment_number"),
        sa.CheckConstraint(
            "principal_pln >= 0 AND interest_pln >= 0 AND fees_pln >= 0 AND principal_pln + interest_pln + fees_pln BETWEEN 1 AND 9007199254740991",
            name="ck_allegro_pay_installment_amount",
        ),
    )
    op.create_table(
        "allegro_pay_allocations",
        *identity(),
        sa.Column("installment_id", sa.UUID(), nullable=False),
        sa.Column("transaction_id", sa.UUID(), nullable=False),
        sa.Column("amount_pln", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint(
            "installment_id", "transaction_id", name="uq_allegro_pay_allocation_pair"
        ),
        sa.ForeignKeyConstraint(
            ["installment_id", "user_id"],
            ["allegro_pay_installments.id", "allegro_pay_installments.user_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id", "user_id"],
            ["financial_transactions.id", "financial_transactions.user_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "amount_pln BETWEEN 1 AND 9007199254740991", name="ck_allegro_pay_allocation_amount"
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table in (
        "allegro_pay_allocations",
        "allegro_pay_installments",
        "allegro_pay_purchases",
        "allegro_pay_profiles",
    ):
        if bind.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar():
            raise RuntimeError("Allegro Pay data exists; downgrade refused")
    for table in (
        "allegro_pay_allocations",
        "allegro_pay_installments",
        "allegro_pay_purchases",
        "allegro_pay_profiles",
    ):
        op.drop_table(table)
