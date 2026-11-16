"""One BO identity per account; its nonzero amount lives only in the ledger."""

import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AccountOpeningBalance(Base):
    __tablename__ = "account_opening_balances"
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_account_opening_balance_account"),
        UniqueConstraint("transaction_id", name="uq_account_opening_balance_transaction"),
        ForeignKeyConstraint(
            ["account_id", "user_id"],
            ["accounts.id", "accounts.user_id"],
            ondelete="CASCADE",
            name="fk_account_opening_balance_account_owner",
        ),
        ForeignKeyConstraint(
            ["transaction_id", "user_id"],
            ["financial_transactions.id", "financial_transactions.user_id"],
            ondelete="RESTRICT",
            name="fk_account_opening_balance_transaction_owner",
        ),
        CheckConstraint("version >= 1", name="ck_account_opening_balance_version"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    opening_date: Mapped[date] = mapped_column(Date, nullable=False)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    version: Mapped[int] = mapped_column(default=1, server_default="1", nullable=False)
