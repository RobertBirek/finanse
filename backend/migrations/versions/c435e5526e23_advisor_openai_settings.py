"""Per-owner OpenAI advisor settings, prompt revisions and usage.

Revision ID: c435e5526e23
Revises: a6e52f41c9d0
"""

import sqlalchemy as sa
from alembic import op

revision = "c435e5526e23"
down_revision = "a6e52f41c9d0"
branch_labels = None
depends_on = None


def _owned_columns():
    return (
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def upgrade() -> None:
    op.create_table(
        "advisor_ai_profiles",
        *_owned_columns(),
        sa.Column("model", sa.String(128)),
        sa.Column("encrypted_key", sa.LargeBinary()),
        sa.UniqueConstraint("user_id"),
    )
    op.create_table(
        "advisor_prompt_versions",
        *_owned_columns(),
        sa.Column("revision", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("instructions", sa.Text()),
        sa.UniqueConstraint("revision"),
    )
    op.create_index(
        "ix_advisor_prompt_versions_owner", "advisor_prompt_versions", ["user_id", "revision"]
    )
    op.create_table(
        "advisor_ai_usage",
        *_owned_columns(),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.BigInteger()),
        sa.Column("output_tokens", sa.BigInteger()),
        sa.CheckConstraint("kind IN ('chat', 'test')", name="ck_advisor_ai_usage_kind"),
        sa.CheckConstraint("duration_ms >= 0", name="ck_advisor_ai_usage_duration"),
        sa.CheckConstraint("input_tokens >= 0", name="ck_advisor_ai_usage_input"),
        sa.CheckConstraint("output_tokens >= 0", name="ck_advisor_ai_usage_output"),
    )
    op.create_index("ix_advisor_ai_usage_owner", "advisor_ai_usage", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("advisor_ai_usage")
    op.drop_table("advisor_prompt_versions")
    op.drop_table("advisor_ai_profiles")
