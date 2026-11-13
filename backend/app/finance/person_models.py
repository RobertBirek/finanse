"""People are metadata identities, never an additional financial account."""

import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FinancePerson(Base):
    __tablename__ = "finance_people"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_finance_person_owner"),
        UniqueConstraint("reference_account_id", name="uq_finance_person_reference_account"),
        ForeignKeyConstraint(
            ["reference_account_id", "user_id"],
            ["accounts.id", "accounts.user_id"],
            ondelete="RESTRICT",
            name="fk_finance_person_reference_account",
        ),
        CheckConstraint("version > 0", name="ck_finance_person_version"),
        CheckConstraint("length(trim(name)) BETWEEN 1 AND 200", name="ck_finance_person_name"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    reference_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )


class PersonTransactionLink(Base):
    __tablename__ = "person_transaction_links"
    __table_args__ = (
        UniqueConstraint("transaction_id", name="uq_person_transaction_link"),
        ForeignKeyConstraint(
            ["person_id", "user_id"],
            ["finance_people.id", "finance_people.user_id"],
            ondelete="RESTRICT",
            name="fk_person_transaction_person",
        ),
        ForeignKeyConstraint(
            ["transaction_id", "user_id"],
            ["financial_transactions.id", "financial_transactions.user_id"],
            ondelete="RESTRICT",
            name="fk_person_transaction_transaction",
        ),
        CheckConstraint("kind = 'gift_received'", name="ck_person_transaction_kind"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), default="gift_received", nullable=False)
