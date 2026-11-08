"""credit card account type

Revision ID: 739144d5eaef
Revises: 00a9ccb532b9
Create Date: 2026-11-08 10:38:13.915949

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "739144d5eaef"
down_revision: str | None = "00a9ccb532b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Do not infer a card from a name or from the generic credit account type.
    # Only an existing, owned profile proves the account is a credit card.
    op.execute(
        sa.text("""
        UPDATE accounts AS a SET type = 'credit_card'
        WHERE a.type <> 'credit_card' AND EXISTS (
            SELECT 1 FROM credit_cards AS c
            WHERE c.account_id = a.id AND c.user_id = a.user_id
        )
    """)
    )


def downgrade() -> None:
    # The old application uses `credit` for profiles too. Retain every profile,
    # statement, plan, posting and amount; this is only a classification change.
    op.execute(sa.text("UPDATE accounts SET type = 'credit' WHERE type = 'credit_card'"))
