"""New-upload finance draft intents; legacy documents are not adopted.

Revision ID: a6e52f41c9d0
Revises: efaf78432563
"""

import sqlalchemy as sa
from alembic import op

revision: str = "a6e52f41c9d0"
down_revision: str | None = "efaf78432563"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_extraction_revisions",
        sa.Column("suggested_category_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_document_revision_suggested_category",
        "document_extraction_revisions",
        "categories",
        ["suggested_category_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "document_finance_draft_intents",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("revision_id", sa.UUID(), nullable=True),
        sa.Column("bill_id", sa.UUID(), nullable=True),
        sa.Column("state", sa.String(20), server_default="pending", nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("document_id", name="uq_document_finance_draft_document"),
        sa.ForeignKeyConstraint(
            ["document_id", "user_id"],
            ["documents.id", "documents.user_id"],
            name="fk_document_finance_draft_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["document_extraction_revisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["bill_id"], ["financial_documents.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "state IN ('pending', 'needs_review', 'failed', 'succeeded')",
            name="ck_document_finance_draft_state",
        ),
    )
    op.create_index(
        "ix_document_finance_draft_state",
        "document_finance_draft_intents",
        ["state", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_finance_draft_state", table_name="document_finance_draft_intents")
    op.drop_table("document_finance_draft_intents")
    op.drop_constraint(
        "fk_document_revision_suggested_category",
        "document_extraction_revisions",
        type_="foreignkey",
    )
    op.drop_column("document_extraction_revisions", "suggested_category_id")
