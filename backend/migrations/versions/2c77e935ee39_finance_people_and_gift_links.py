"""finance people and gift links

Revision ID: 2c77e935ee39
Revises: 3254a4781542
Create Date: 2026-11-13 09:03:46.774304

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2c77e935ee39"
down_revision: Union[str, None] = "3254a4781542"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint("uq_account_id_owner", "accounts", ["id", "user_id"])
    op.create_table(
        "finance_people",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("reference_account_id", sa.UUID(), nullable=True),
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
        sa.CheckConstraint("length(trim(name)) BETWEEN 1 AND 200", name="ck_finance_person_name"),
        sa.CheckConstraint("version > 0", name="ck_finance_person_version"),
        sa.ForeignKeyConstraint(
            ["reference_account_id", "user_id"],
            ["accounts.id", "accounts.user_id"],
            name="fk_finance_person_reference_account",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "user_id", name="uq_finance_person_owner"),
        sa.UniqueConstraint("reference_account_id", name="uq_finance_person_reference_account"),
    )
    op.create_index(op.f("ix_finance_people_user_id"), "finance_people", ["user_id"], unique=False)
    op.create_table(
        "person_transaction_links",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("person_id", sa.UUID(), nullable=False),
        sa.Column("transaction_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
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
        sa.CheckConstraint("kind = 'gift_received'", name="ck_person_transaction_kind"),
        sa.ForeignKeyConstraint(
            ["person_id", "user_id"],
            ["finance_people.id", "finance_people.user_id"],
            name="fk_person_transaction_person",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id", "user_id"],
            ["financial_transactions.id", "financial_transactions.user_id"],
            name="fk_person_transaction_transaction",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transaction_id", name="uq_person_transaction_link"),
    )
    op.create_index(
        op.f("ix_person_transaction_links_person_id"),
        "person_transaction_links",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_transaction_links_user_id"),
        "person_transaction_links",
        ["user_id"],
        unique=False,
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    for table in ["finance_people", "person_transaction_links"]:
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table})")):
            raise RuntimeError("Cannot downgrade populated finance people")
    op.drop_index(
        op.f("ix_person_transaction_links_user_id"), table_name="person_transaction_links"
    )
    op.drop_index(
        op.f("ix_person_transaction_links_person_id"), table_name="person_transaction_links"
    )
    op.drop_table("person_transaction_links")
    op.drop_index(op.f("ix_finance_people_user_id"), table_name="finance_people")
    op.drop_table("finance_people")
    op.drop_constraint("uq_account_id_owner", "accounts", type_="unique")
    # ### end Alembic commands ###
