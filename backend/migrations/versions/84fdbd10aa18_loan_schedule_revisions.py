"""loan_schedule_revisions

Revision ID: 84fdbd10aa18
Revises: 6bd8758ebc7d
Create Date: 2026-11-10 07:27:19.145496

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "84fdbd10aa18"
down_revision: Union[str, None] = "6bd8758ebc7d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Referenced owner keys must exist before creating their dependent tables.
    op.create_unique_constraint(
        "uq_bank_import_revision_owner", "bank_import_revisions", ["id", "user_id"]
    )
    op.create_unique_constraint("uq_bank_import_row_owner", "bank_import_rows", ["id", "user_id"])
    op.create_unique_constraint(
        "uq_finance_command_receipt_owner", "finance_command_receipts", ["id", "user_id"]
    )
    op.create_unique_constraint("uq_loan_agreement_owner", "loan_agreements", ["id", "user_id"])
    op.create_unique_constraint(
        "uq_loan_installment_owner_loan", "loan_installments", ["id", "user_id", "loan_id"]
    )
    op.create_table(
        "loan_schedule_revisions",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("loan_id", sa.UUID(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("previous_revision_id", sa.UUID(), nullable=True),
        sa.Column("source_revision_id", sa.UUID(), nullable=True),
        sa.Column("receipt_id", sa.UUID(), nullable=False),
        sa.Column("bank_effective_date", sa.Date(), nullable=True),
        sa.Column("activated_on", sa.Date(), nullable=False),
        sa.Column("cutover_date", sa.Date(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(kind = 'manual_baseline' AND source_revision_id IS NULL) OR (kind = 'bank_import' AND source_revision_id IS NOT NULL)",
            name="ck_loan_schedule_revision_source",
        ),
        sa.CheckConstraint(
            "kind IN ('manual_baseline','bank_import')", name="ck_loan_schedule_revision_kind"
        ),
        sa.CheckConstraint(
            "state IN ('active','superseded')", name="ck_loan_schedule_revision_state"
        ),
        sa.CheckConstraint("ordinal > 0", name="ck_loan_schedule_revision_ordinal"),
        sa.ForeignKeyConstraint(
            ["loan_id", "user_id"],
            ["loan_agreements.id", "loan_agreements.user_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["previous_revision_id", "user_id", "loan_id"],
            [
                "loan_schedule_revisions.id",
                "loan_schedule_revisions.user_id",
                "loan_schedule_revisions.loan_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["receipt_id", "user_id"],
            ["finance_command_receipts.id", "finance_command_receipts.user_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_revision_id", "user_id"],
            ["bank_import_revisions.id", "bank_import_revisions.user_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "user_id", "loan_id", name="uq_loan_schedule_revision_owner_loan"
        ),
        sa.UniqueConstraint("loan_id", "ordinal", name="uq_loan_schedule_revision_ordinal"),
    )
    op.create_index(
        op.f("ix_loan_schedule_revisions_loan_id"),
        "loan_schedule_revisions",
        ["loan_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_loan_schedule_revisions_user_id"),
        "loan_schedule_revisions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "uq_loan_schedule_active",
        "loan_schedule_revisions",
        ["loan_id"],
        unique=True,
        postgresql_where=sa.text("state = 'active'"),
    )
    op.create_table(
        "loan_schedule_memberships",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("loan_id", sa.UUID(), nullable=False),
        sa.Column("revision_id", sa.UUID(), nullable=False),
        sa.Column("installment_id", sa.UUID(), nullable=False),
        sa.Column("bank_number", sa.Integer(), nullable=True),
        sa.Column("source_row_id", sa.UUID(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("principal_pln", sa.BigInteger(), nullable=False),
        sa.Column("interest_pln", sa.BigInteger(), nullable=False),
        sa.Column("fees_pln", sa.BigInteger(), nullable=False),
        sa.Column("balance_after_pln", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(bank_number IS NULL) = (source_row_id IS NULL)",
            name="ck_loan_schedule_membership_provenance",
        ),
        sa.CheckConstraint(
            "balance_after_pln IS NULL OR balance_after_pln BETWEEN 0 AND 9007199254740991",
            name="ck_loan_schedule_membership_balance",
        ),
        sa.CheckConstraint(
            "bank_number IS NULL OR bank_number > 0", name="ck_loan_schedule_membership_bank_number"
        ),
        sa.CheckConstraint(
            "principal_pln + interest_pln + fees_pln BETWEEN 1 AND 9007199254740991",
            name="ck_loan_schedule_membership_total",
        ),
        sa.CheckConstraint(
            "principal_pln >= 0 AND interest_pln >= 0 AND fees_pln >= 0",
            name="ck_loan_schedule_membership_components",
        ),
        sa.ForeignKeyConstraint(
            ["installment_id", "user_id", "loan_id"],
            ["loan_installments.id", "loan_installments.user_id", "loan_installments.loan_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["revision_id", "user_id", "loan_id"],
            [
                "loan_schedule_revisions.id",
                "loan_schedule_revisions.user_id",
                "loan_schedule_revisions.loan_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_row_id", "user_id"],
            ["bank_import_rows.id", "bank_import_rows.user_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "revision_id", "bank_number", name="uq_loan_schedule_membership_bank_number"
        ),
        sa.UniqueConstraint(
            "revision_id", "installment_id", name="uq_loan_schedule_membership_installment"
        ),
    )
    op.create_index(
        op.f("ix_loan_schedule_memberships_installment_id"),
        "loan_schedule_memberships",
        ["installment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_loan_schedule_memberships_loan_id"),
        "loan_schedule_memberships",
        ["loan_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_loan_schedule_memberships_revision_id"),
        "loan_schedule_memberships",
        ["revision_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_loan_schedule_memberships_user_id"),
        "loan_schedule_memberships",
        ["user_id"],
        unique=False,
    )
    op.add_column(
        "loan_agreements", sa.Column("active_schedule_revision_id", sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        "fk_loan_active_schedule_revision",
        "loan_agreements",
        "loan_schedule_revisions",
        ["active_schedule_revision_id", "user_id", "id"],
        ["id", "user_id", "loan_id"],
        ondelete="RESTRICT",
        use_alter=True,
    )
    op.add_column(
        "loan_installments", sa.Column("superseded_by_revision_id", sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        "fk_loan_installment_superseded_revision",
        "loan_installments",
        "loan_schedule_revisions",
        ["superseded_by_revision_id", "user_id", "loan_id"],
        ["id", "user_id", "loan_id"],
        ondelete="RESTRICT",
        use_alter=True,
    )


def downgrade() -> None:
    used = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS(SELECT 1 FROM loan_schedule_revisions) "
                "OR EXISTS(SELECT 1 FROM loan_schedule_memberships) "
                "OR EXISTS(SELECT 1 FROM loan_agreements WHERE active_schedule_revision_id IS NOT NULL) "
                "OR EXISTS(SELECT 1 FROM loan_installments WHERE superseded_by_revision_id IS NOT NULL)"
            )
        )
        .scalar()
    )
    if used:
        raise RuntimeError("Cannot downgrade: loan schedule data or provenance exists")
    op.drop_constraint(
        "fk_loan_installment_superseded_revision", "loan_installments", type_="foreignkey"
    )
    op.drop_column("loan_installments", "superseded_by_revision_id")
    op.drop_constraint("fk_loan_active_schedule_revision", "loan_agreements", type_="foreignkey")
    op.drop_column("loan_agreements", "active_schedule_revision_id")
    op.drop_index(
        op.f("ix_loan_schedule_memberships_user_id"), table_name="loan_schedule_memberships"
    )
    op.drop_index(
        op.f("ix_loan_schedule_memberships_revision_id"), table_name="loan_schedule_memberships"
    )
    op.drop_index(
        op.f("ix_loan_schedule_memberships_loan_id"), table_name="loan_schedule_memberships"
    )
    op.drop_index(
        op.f("ix_loan_schedule_memberships_installment_id"), table_name="loan_schedule_memberships"
    )
    op.drop_table("loan_schedule_memberships")
    op.drop_index(
        "uq_loan_schedule_active",
        table_name="loan_schedule_revisions",
        postgresql_where=sa.text("state = 'active'"),
    )
    op.drop_index(op.f("ix_loan_schedule_revisions_user_id"), table_name="loan_schedule_revisions")
    op.drop_index(op.f("ix_loan_schedule_revisions_loan_id"), table_name="loan_schedule_revisions")
    op.drop_table("loan_schedule_revisions")
    op.drop_constraint("uq_loan_installment_owner_loan", "loan_installments", type_="unique")
    op.drop_constraint("uq_loan_agreement_owner", "loan_agreements", type_="unique")
    op.drop_constraint(
        "uq_finance_command_receipt_owner", "finance_command_receipts", type_="unique"
    )
    op.drop_constraint("uq_bank_import_row_owner", "bank_import_rows", type_="unique")
    op.drop_constraint("uq_bank_import_revision_owner", "bank_import_revisions", type_="unique")
