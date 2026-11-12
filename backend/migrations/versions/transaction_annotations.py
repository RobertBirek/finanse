"""transaction_annotations

Revision ID: 3254a4781542
Revises: 84fdbd10aa18
Create Date: 2026-11-12 17:52:29.663972

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3254a4781542"
down_revision: str | None = "84fdbd10aa18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    invalid = op.get_bind().scalar(
        sa.text("""
        SELECT count(*) FROM financial_transactions t LEFT JOIN projects p ON p.id=t.project_id
        WHERE t.project_id IS NOT NULL AND (p.id IS NULL OR p.user_id<>t.user_id)
    """)
    )
    if invalid:
        raise RuntimeError(
            "Transaction annotations: invalid project references; explicit reconciliation required"
        )
    op.create_unique_constraint(
        "uq_financial_transaction_id_owner", "financial_transactions", ["id", "user_id"]
    )
    op.create_foreign_key(
        "fk_financial_transaction_project",
        "financial_transactions",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "finance_tags",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "user_id", name="uq_finance_tag_id_owner"),
        sa.UniqueConstraint("user_id", "normalized_name", name="uq_finance_tag_owner_name"),
    )
    op.create_index(op.f("ix_finance_tags_user_id"), "finance_tags", ["user_id"], unique=False)
    op.create_table(
        "transaction_annotations",
        sa.Column("transaction_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("display_description", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
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
        sa.CheckConstraint("version > 0", name="ck_transaction_annotation_version"),
        sa.ForeignKeyConstraint(
            ["transaction_id", "user_id"],
            ["financial_transactions.id", "financial_transactions.user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transaction_id", name="uq_transaction_annotation_transaction"),
    )
    op.create_index(
        op.f("ix_transaction_annotations_user_id"),
        "transaction_annotations",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "transaction_tags",
        sa.Column("transaction_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("tag_id", sa.UUID(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["tag_id", "user_id"], ["finance_tags.id", "finance_tags.user_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id", "user_id"],
            ["financial_transactions.id", "financial_transactions.user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transaction_id", "tag_id", name="uq_transaction_tag_link"),
    )
    op.create_index(
        op.f("ix_transaction_tags_transaction_id"),
        "transaction_tags",
        ["transaction_id"],
        unique=False,
    )


def downgrade() -> None:
    for table in ["transaction_annotations", "transaction_tags", "finance_tags"]:
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table})")):
            raise RuntimeError("Cannot downgrade populated transaction annotations")
    op.drop_index(op.f("ix_transaction_tags_transaction_id"), table_name="transaction_tags")
    op.drop_table("transaction_tags")
    op.drop_index(op.f("ix_transaction_annotations_user_id"), table_name="transaction_annotations")
    op.drop_table("transaction_annotations")
    op.drop_index(op.f("ix_finance_tags_user_id"), table_name="finance_tags")
    op.drop_table("finance_tags")
    op.drop_constraint(
        "fk_financial_transaction_project", "financial_transactions", type_="foreignkey"
    )
    op.drop_constraint(
        "uq_financial_transaction_id_owner", "financial_transactions", type_="unique"
    )
