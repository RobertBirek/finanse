"""Store statement auto-post permission and durable, revision-scoped requests."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "5f1d54d40a2e"
down_revision = "e5a46dc32772"
branch_labels = None
depends_on = None

_SETTINGS = "bank_import_auto_post_settings"
_JOBS = "bank_import_auto_post_jobs"
_SOURCES = "bank_import_sources"


def _identity_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
    )


def upgrade() -> None:
    op.add_column(_SOURCES, sa.Column("auto_post_epoch", sa.Integer()))
    op.create_table(
        _SETTINGS,
        *_identity_columns(),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("epoch", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "expense_category_id", sa.UUID(), sa.ForeignKey("categories.id", ondelete="SET NULL")
        ),
        sa.Column(
            "income_category_id", sa.UUID(), sa.ForeignKey("categories.id", ondelete="SET NULL")
        ),
        sa.UniqueConstraint("user_id", name="uq_bank_import_auto_post_settings_owner"),
        sa.CheckConstraint("epoch > 0", name="ck_bank_import_auto_post_epoch"),
    )
    op.create_index(f"ix_{_SETTINGS}_user_id", _SETTINGS, ["user_id"])
    op.create_table(
        _JOBS,
        *_identity_columns(),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("revision_id", sa.UUID(), nullable=False),
        sa.Column("manual", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("policy_epoch", sa.Integer()),
        sa.Column("account_id", sa.UUID()),
        sa.Column("state", sa.String(10), server_default="queued", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("reason", sa.String(60)),
        sa.Column("posted_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("row_reasons", JSONB(), server_default="{}", nullable=False),
        sa.CheckConstraint("state IN ('queued','done')", name="ck_bank_import_auto_post_state"),
        sa.UniqueConstraint("revision_id", name="uq_bank_import_auto_post_revision"),
        sa.ForeignKeyConstraint(
            ["revision_id", "user_id", "source_id"],
            [
                "bank_import_revisions.id",
                "bank_import_revisions.user_id",
                "bank_import_revisions.source_id",
            ],
            ondelete="RESTRICT",
        ),
    )
    for column in ("source_id", "user_id"):
        op.create_index(f"ix_{_JOBS}_{column}", _JOBS, [column])
    op.create_index("ix_bank_import_auto_post_due", _JOBS, ["state", "next_attempt_at"])


def downgrade() -> None:
    connection = op.get_bind()
    op.execute(f"LOCK TABLE {_SOURCES}, {_SETTINGS}, {_JOBS} IN ACCESS EXCLUSIVE MODE")
    if any(
        connection.scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table} {where})"))
        for table, where in (
            (_SETTINGS, ""),
            (_JOBS, ""),
            (_SOURCES, "WHERE auto_post_epoch IS NOT NULL"),
        )
    ):
        raise RuntimeError("Preserve auto-post grants and audit history; use app-only rollback")
    op.drop_table(_JOBS)
    op.drop_table(_SETTINGS)
    op.drop_column(_SOURCES, "auto_post_epoch")
