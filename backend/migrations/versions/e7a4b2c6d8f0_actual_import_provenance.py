"""actual import provenance

Revision ID: e7a4b2c6d8f0
Revises: d5f9a1c2b3e4
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7a4b2c6d8f0"
down_revision: str | None = "d5f9a1c2b3e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "actual_import_mappings",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("entity_type", sa.String(length=30), nullable=False),
        sa.Column("actual_id", sa.String(length=255), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "entity_type", "actual_id", name="uq_actual_import_mapping"),
    )
    op.create_index(
        op.f("ix_actual_import_mappings_user_id"),
        "actual_import_mappings",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_actual_import_mappings_user_id"), table_name="actual_import_mappings")
    op.drop_table("actual_import_mappings")
