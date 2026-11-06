"""add account and category colors

Revision ID: f3a9d17c2e4b
Revises: 7b57f2f0bde6
Create Date: 2026-11-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f3a9d17c2e4b"
down_revision: str | None = "7b57f2f0bde6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("color", sa.String(length=7), nullable=True))
    op.create_check_constraint(
        "ck_accounts_color_hex",
        "accounts",
        "color IS NULL OR color ~ '^#[0-9A-F]{6}$'",
    )
    op.add_column("categories", sa.Column("color", sa.String(length=7), nullable=True))
    op.create_check_constraint(
        "ck_categories_color_hex",
        "categories",
        "color IS NULL OR color ~ '^#[0-9A-F]{6}$'",
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE accounts, categories IN ACCESS EXCLUSIVE MODE"))
    saved = connection.scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM accounts WHERE color IS NOT NULL) OR EXISTS(SELECT 1 FROM categories WHERE color IS NOT NULL)"
        )
    )
    if saved:
        raise RuntimeError("Refusing downgrade: saved colors would be lost")
    op.drop_constraint("ck_categories_color_hex", "categories", type_="check")
    op.drop_column("categories", "color")
    op.drop_constraint("ck_accounts_color_hex", "accounts", type_="check")
    op.drop_column("accounts", "color")
