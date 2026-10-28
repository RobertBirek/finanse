"""add loan schedule plans and payment links

Revision ID: c2d7e9a4f801
Revises: b8e4c2f1a7d9
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c2d7e9a4f801"
down_revision: str | None = "b8e4c2f1a7d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "loan_agreements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "payment_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint("account_id <> payment_account_id", name="ck_loan_distinct_accounts"),
        sa.UniqueConstraint("account_id", name="uq_loan_agreement_account"),
    )
    op.create_index("ix_loan_agreements_user_id", "loan_agreements", ["user_id"])
    op.create_table(
        "loan_installments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "loan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("loan_agreements.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("principal_pln", sa.BigInteger(), nullable=False),
        sa.Column("interest_pln", sa.BigInteger(), nullable=False),
        sa.Column("fees_pln", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("loan_id", "number", name="uq_loan_installment_number"),
        sa.CheckConstraint("number > 0", name="ck_loan_installment_number"),
        sa.CheckConstraint(
            "principal_pln >= 0 AND interest_pln >= 0 AND fees_pln >= 0",
            name="ck_loan_installment_components",
        ),
        sa.CheckConstraint(
            "principal_pln + interest_pln + fees_pln > 0", name="ck_loan_installment_total"
        ),
        sa.CheckConstraint(
            "principal_pln + interest_pln + fees_pln <= 9007199254740991",
            name="ck_loan_installment_safe_total",
        ),
    )
    op.create_index("ix_loan_installments_user_id", "loan_installments", ["user_id"])
    op.create_index("ix_loan_installments_loan_id", "loan_installments", ["loan_id"])
    op.create_table(
        "loan_payment_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "installment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("loan_installments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("financial_transactions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.UniqueConstraint("transaction_id"),
    )
    op.create_index("ix_loan_payment_links_user_id", "loan_payment_links", ["user_id"])
    op.create_index(
        "ix_loan_payment_links_installment_id", "loan_payment_links", ["installment_id"]
    )


def downgrade() -> None:
    op.drop_table("loan_payment_links")
    op.drop_table("loan_installments")
    op.drop_table("loan_agreements")
