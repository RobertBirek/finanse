"""Card metadata references the ledger; never another independently editable balance."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CreditCard(Base):
    __tablename__ = "credit_cards"
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), unique=True
    )
    limit_pln: Mapped[int] = mapped_column(BigInteger)
    apr: Mapped[Decimal] = mapped_column(Numeric(7, 4))
    cycle_close_day: Mapped[int] = mapped_column(Integer)
    due_day: Mapped[int] = mapped_column(Integer)
    grace_days: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        CheckConstraint("limit_pln > 0 AND limit_pln <= 9007199254740991", name="ck_card_limit"),
        CheckConstraint("apr >= 0 AND apr <= 100", name="ck_card_apr"),
        CheckConstraint(
            "cycle_close_day BETWEEN 1 AND 31 AND due_day BETWEEN 1 AND 31 AND grace_days BETWEEN 0 AND 366 AND version > 0",
            name="ck_card_terms",
        ),
    )


class CardRecord(Base):
    __abstract__ = True
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("credit_cards.id", ondelete="RESTRICT"), index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSONB)


class CardStatement(CardRecord):
    __tablename__ = "card_statements"
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    debt_pln: Mapped[int] = mapped_column(BigInteger)
    minimum_pln: Mapped[int] = mapped_column(BigInteger)
    source_reference: Mapped[str] = mapped_column(String(300))
    __table_args__ = (
        UniqueConstraint("card_id", "request_id", name="uq_card_statement_request"),
        UniqueConstraint("card_id", "period_end", name="uq_card_statement_period"),
        CheckConstraint(
            "period_start <= period_end AND period_end < due_date", name="ck_card_statement_dates"
        ),
        CheckConstraint(
            "debt_pln BETWEEN 0 AND 9007199254740991 AND minimum_pln BETWEEN 0 AND debt_pln",
            name="ck_card_statement_amounts",
        ),
    )


class CardPlan(CardRecord):
    __tablename__ = "card_plans"
    name: Mapped[str] = mapped_column(String(200))
    source_transaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("financial_transactions.id", ondelete="RESTRICT"), index=True
    )
    principal_pln: Mapped[int] = mapped_column(BigInteger)
    apr: Mapped[Decimal] = mapped_column(Numeric(7, 4))
    fees_pln: Mapped[int] = mapped_column(BigInteger)
    schedule_kind: Mapped[str] = mapped_column(String(20), default="estimated")
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        UniqueConstraint("card_id", "request_id", name="uq_card_plan_request"),
        CheckConstraint(
            "principal_pln BETWEEN 1 AND 9007199254740991 AND fees_pln BETWEEN 0 AND 9007199254740991",
            name="ck_card_plan_amounts",
        ),
        CheckConstraint("apr >= 0 AND apr <= 100 AND version > 0", name="ck_card_plan_terms"),
        CheckConstraint("schedule_kind IN ('estimated', 'bank')", name="ck_card_plan_schedule"),
    )


class CardInstallment(Base):
    __tablename__ = "card_installments"
    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("card_plans.id", ondelete="RESTRICT"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    due_date: Mapped[date] = mapped_column(Date)
    principal_pln: Mapped[int] = mapped_column(BigInteger)
    interest_pln: Mapped[int] = mapped_column(BigInteger)
    fees_pln: Mapped[int] = mapped_column(BigInteger)
    __table_args__ = (
        UniqueConstraint("plan_id", "number", name="uq_card_installment_number"),
        CheckConstraint(
            "number BETWEEN 1 AND 600 AND principal_pln > 0 AND interest_pln >= 0 AND fees_pln >= 0 AND principal_pln + interest_pln + fees_pln <= 9007199254740991",
            name="ck_card_installment_amounts",
        ),
    )


class CardAllocation(CardRecord):
    __tablename__ = "card_allocations"
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("financial_transactions.id", ondelete="RESTRICT"), index=True
    )
    statement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("card_statements.id", ondelete="RESTRICT")
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("card_plans.id", ondelete="RESTRICT")
    )
    amount_pln: Mapped[int] = mapped_column(BigInteger)
    principal_pln: Mapped[int] = mapped_column(BigInteger, default=0)
    interest_pln: Mapped[int] = mapped_column(BigInteger, default=0)
    fees_pln: Mapped[int] = mapped_column(BigInteger, default=0)
    __table_args__ = (
        UniqueConstraint("card_id", "request_id", name="uq_card_allocation_request"),
        CheckConstraint(
            "(statement_id IS NULL) <> (plan_id IS NULL)", name="ck_card_allocation_target"
        ),
        CheckConstraint(
            "amount_pln BETWEEN 1 AND 9007199254740991 AND principal_pln >= 0 AND interest_pln >= 0 AND fees_pln >= 0",
            name="ck_card_allocation_amounts",
        ),
        CheckConstraint(
            "(plan_id IS NOT NULL AND principal_pln + interest_pln + fees_pln = amount_pln) OR (statement_id IS NOT NULL AND principal_pln + interest_pln + fees_pln = 0)",
            name="ck_card_allocation_components",
        ),
    )


class CardCharge(CardRecord):
    __tablename__ = "card_charges"
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("financial_transactions.id", ondelete="RESTRICT"), unique=True
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("card_plans.id", ondelete="RESTRICT")
    )
    kind: Mapped[str] = mapped_column(String(30))
    amount_pln: Mapped[int] = mapped_column(BigInteger)
    description: Mapped[str] = mapped_column(String(300))
    booking_date: Mapped[date] = mapped_column(Date)
    __table_args__ = (
        UniqueConstraint("card_id", "request_id", name="uq_card_charge_request"),
        CheckConstraint("amount_pln BETWEEN 1 AND 9007199254740991", name="ck_card_charge_amount"),
        CheckConstraint(
            "kind IN ('interest', 'fee', 'interest_refund', 'fee_refund')",
            name="ck_card_charge_kind",
        ),
    )
