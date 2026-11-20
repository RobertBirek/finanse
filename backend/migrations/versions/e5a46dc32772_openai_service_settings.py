"""Isolate OpenAI settings and telemetry by application purpose.

Revision ID: e5a46dc32772
Revises: c435e5526e23
"""

import sqlalchemy as sa
from alembic import op

revision = "e5a46dc32772"
down_revision = "c435e5526e23"
branch_labels = None
depends_on = None

_TABLES = ("advisor_ai_profiles", "advisor_prompt_versions", "advisor_ai_usage")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table, sa.Column("purpose", sa.String(20), server_default="advisor", nullable=False)
        )
    op.add_column("advisor_ai_profiles", sa.Column("configuration_id", sa.UUID()))
    op.drop_constraint("advisor_ai_profiles_user_id_key", "advisor_ai_profiles", type_="unique")
    op.create_unique_constraint(
        "uq_advisor_ai_profile_purpose", "advisor_ai_profiles", ["user_id", "purpose"]
    )
    op.drop_index("ix_advisor_prompt_versions_owner", table_name="advisor_prompt_versions")
    op.create_index(
        "ix_advisor_prompt_versions_owner",
        "advisor_prompt_versions",
        ["user_id", "purpose", "revision"],
    )
    op.drop_index("ix_advisor_ai_usage_owner", table_name="advisor_ai_usage")
    op.create_index(
        "ix_advisor_ai_usage_owner", "advisor_ai_usage", ["user_id", "purpose", "created_at"]
    )
    op.drop_constraint("ck_advisor_ai_usage_kind", "advisor_ai_usage", type_="check")
    op.alter_column("advisor_ai_usage", "kind", type_=sa.String(9), existing_type=sa.String(8))
    op.create_check_constraint(
        "ck_advisor_ai_usage_kind", "advisor_ai_usage", "kind IN ('chat', 'test', 'operation')"
    )


def downgrade() -> None:
    # App-only rollback to the pre-AI version needs no schema downgrade.
    # On the schema path fail closed rather than losing new-purpose rows.
    connection = op.get_bind()
    for table in _TABLES:
        op.execute(f'LOCK TABLE "{table}" IN ACCESS EXCLUSIVE MODE')
        if connection.scalar(
            sa.text(f"SELECT EXISTS(SELECT 1 FROM \"{table}\" WHERE purpose <> 'advisor')")
        ):
            raise RuntimeError("OpenAI settings for other purposes must be retained")
    if connection.scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM advisor_ai_usage WHERE kind = 'operation')")
    ) or connection.scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM advisor_ai_profiles WHERE configuration_id IS NOT NULL)"
        )
    ):
        raise RuntimeError("OpenAI configuration generations and usage must be retained")
    op.drop_constraint("ck_advisor_ai_usage_kind", "advisor_ai_usage", type_="check")
    op.create_check_constraint(
        "ck_advisor_ai_usage_kind", "advisor_ai_usage", "kind IN ('chat', 'test')"
    )
    op.alter_column("advisor_ai_usage", "kind", type_=sa.String(8), existing_type=sa.String(9))
    op.drop_index("ix_advisor_ai_usage_owner", table_name="advisor_ai_usage")
    op.create_index("ix_advisor_ai_usage_owner", "advisor_ai_usage", ["user_id", "created_at"])
    op.drop_index("ix_advisor_prompt_versions_owner", table_name="advisor_prompt_versions")
    op.create_index(
        "ix_advisor_prompt_versions_owner", "advisor_prompt_versions", ["user_id", "revision"]
    )
    op.drop_constraint("uq_advisor_ai_profile_purpose", "advisor_ai_profiles", type_="unique")
    op.create_unique_constraint(
        "advisor_ai_profiles_user_id_key", "advisor_ai_profiles", ["user_id"]
    )
    op.drop_column("advisor_ai_profiles", "configuration_id")
    for table in reversed(_TABLES):
        op.drop_column(table, "purpose")
