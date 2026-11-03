"""document archive lifecycle

Revision ID: 2f4b2c2a527c
Revises: 92eef8e8086c
Create Date: 2026-11-03 11:16:48.291540

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2f4b2c2a527c"
down_revision: Union[str, None] = "92eef8e8086c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Application rollback must retain archive state, not silently resurrect documents.
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM documents WHERE archived_at IS NOT NULL)")
    ):
        raise RuntimeError("Cannot discard document archive state; keep the additive schema")
    op.drop_column("documents", "archived_at")
