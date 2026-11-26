"""Allegro Pay purchase schedules and allocations referencing ledger entries."""

import uuid
from datetime import date

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AllegroPayProfile(Base):
    __tablename__ = "allegro_pay_profiles"
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    limit_pln: Mapped[int | None] = mapped_column(BigInteger)
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_allegro_pay_account"),
        UniqueConstraint("id", "user_id", name="uq_allegro_pay_profile_owner"),
        ForeignKeyConstraint(
            ["account_id", "user_id"], ["accounts.id", "accounts.user_id"], ondelete="RESTRICT"
        ),
        CheckConstraint(
            "limit_pln IS NULL OR limit_pln BETWEEN 1 AND 9007199254740991",
            name="ck_allegro_pay_limit",
        ),
    )


class AllegroPayPurchase(Base):
    __tablename__ = "allegro_pay_purchases"
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    principal_pln: Mapped[int] = mapped_column(BigInteger, nullable=False)
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_allegro_pay_purchase_owner"),
        UniqueConstraint("transaction_id", name="uq_allegro_pay_purchase_transaction"),
        UniqueConstraint("profile_id", "request_id", name="uq_allegro_pay_purchase_request"),
        ForeignKeyConstraint(
            ["profile_id", "user_id"],
            ["allegro_pay_profiles.id", "allegro_pay_profiles.user_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["transaction_id", "user_id"],
            ["financial_transactions.id", "financial_transactions.user_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "principal_pln BETWEEN 1 AND 9007199254740991", name="ck_allegro_pay_purchase_principal"
        ),
    )


class AllegroPayInstallment(Base):
    __tablename__ = "allegro_pay_installments"
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    purchase_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    number: Mapped[int] = mapped_column(nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    principal_pln: Mapped[int] = mapped_column(BigInteger, nullable=False)
    interest_pln: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fees_pln: Mapped[int] = mapped_column(BigInteger, nullable=False)
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_allegro_pay_installment_owner"),
        UniqueConstraint("purchase_id", "number", name="uq_allegro_pay_installment_number"),
        ForeignKeyConstraint(
            ["purchase_id", "user_id"],
            ["allegro_pay_purchases.id", "allegro_pay_purchases.user_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("number > 0", name="ck_allegro_pay_installment_number"),
        CheckConstraint(
            "principal_pln >= 0 AND interest_pln >= 0 AND fees_pln >= 0 AND principal_pln + interest_pln + fees_pln BETWEEN 1 AND 9007199254740991",
            name="ck_allegro_pay_installment_amount",
        ),
    )


class AllegroPayAllocation(Base):
    __tablename__ = "allegro_pay_allocations"
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    installment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    amount_pln: Mapped[int] = mapped_column(BigInteger, nullable=False)
    __table_args__ = (
        UniqueConstraint("installment_id", "transaction_id", name="uq_allegro_pay_allocation_pair"),
        ForeignKeyConstraint(
            ["installment_id", "user_id"],
            ["allegro_pay_installments.id", "allegro_pay_installments.user_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["transaction_id", "user_id"],
            ["financial_transactions.id", "financial_transactions.user_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "amount_pln BETWEEN 1 AND 9007199254740991", name="ck_allegro_pay_allocation_amount"
        ),
    )
