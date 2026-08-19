"""server side sessions

Revision ID: c9d8e7f6a5b4
Revises: 1dbfe88dfb1b
Create Date: 2026-08-19
"""

import hashlib
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9d8e7f6a5b4"
down_revision: str | None = "1dbfe88dfb1b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _legacy_hash(session_id: object, purpose: str) -> str:
    return hashlib.sha256(f"legacy-session:{purpose}:{session_id}".encode("utf-8")).hexdigest()


def upgrade() -> None:
    op.add_column("sessions", sa.Column("csrf_token_hash", sa.String(length=64), nullable=True))
    op.add_column("sessions", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sessions", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))

    bind = op.get_bind()
    session_ids = bind.execute(sa.text("SELECT id FROM sessions")).scalars()
    for session_id in session_ids:
        bind.execute(
            sa.text(
                "UPDATE sessions SET token_hash = :token_hash, csrf_token_hash = :csrf_token_hash, "
                "revoked_at = now() WHERE id = :id"
            ),
            {
                "id": session_id,
                "token_hash": _legacy_hash(session_id, "token"),
                "csrf_token_hash": _legacy_hash(session_id, "csrf"),
            },
        )

    op.alter_column("sessions", "csrf_token_hash", nullable=False)
    op.create_index("ix_sessions_token_hash", "sessions", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_sessions_token_hash", table_name="sessions")
    op.drop_column("sessions", "last_seen_at")
    op.drop_column("sessions", "revoked_at")
    op.drop_column("sessions", "csrf_token_hash")
