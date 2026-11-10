"""Explicit schedule versions and provenance snapshots; never ledger balances."""

import uuid
from datetime import date

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LoanScheduleRevision(Base):
    __tablename__ = "loan_schedule_revisions"
    __table_args__ = (
        UniqueConstraint("loan_id", "ordinal", name="uq_loan_schedule_revision_ordinal"),
        UniqueConstraint("id", "user_id", "loan_id", name="uq_loan_schedule_revision_owner_loan"),
        ForeignKeyConstraint(
            ["loan_id", "user_id"],
            ["loan_agreements.id", "loan_agreements.user_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["previous_revision_id", "user_id", "loan_id"],
            [
                "loan_schedule_revisions.id",
                "loan_schedule_revisions.user_id",
                "loan_schedule_revisions.loan_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_revision_id", "user_id"],
            ["bank_import_revisions.id", "bank_import_revisions.user_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["receipt_id", "user_id"],
            ["finance_command_receipts.id", "finance_command_receipts.user_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("ordinal > 0", name="ck_loan_schedule_revision_ordinal"),
        CheckConstraint(
            "kind IN ('manual_baseline','bank_import')", name="ck_loan_schedule_revision_kind"
        ),
        CheckConstraint("state IN ('active','superseded')", name="ck_loan_schedule_revision_state"),
        CheckConstraint(
            "(kind = 'manual_baseline' AND source_revision_id IS NULL) OR (kind = 'bank_import' AND source_revision_id IS NOT NULL)",
            name="ck_loan_schedule_revision_source",
        ),
        Index(
            "uq_loan_schedule_active",
            "loan_id",
            unique=True,
            postgresql_where=text("state = 'active'"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    loan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))
    state: Mapped[str] = mapped_column(String(20))
    previous_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    receipt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    bank_effective_date: Mapped[date | None] = mapped_column(Date)
    activated_on: Mapped[date] = mapped_column(Date)
    cutover_date: Mapped[date] = mapped_column(Date)


class LoanScheduleMembership(Base):
    __tablename__ = "loan_schedule_memberships"
    __table_args__ = (
        UniqueConstraint(
            "revision_id", "installment_id", name="uq_loan_schedule_membership_installment"
        ),
        UniqueConstraint(
            "revision_id", "bank_number", name="uq_loan_schedule_membership_bank_number"
        ),
        ForeignKeyConstraint(
            ["revision_id", "user_id", "loan_id"],
            [
                "loan_schedule_revisions.id",
                "loan_schedule_revisions.user_id",
                "loan_schedule_revisions.loan_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["installment_id", "user_id", "loan_id"],
            ["loan_installments.id", "loan_installments.user_id", "loan_installments.loan_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_row_id", "user_id"],
            ["bank_import_rows.id", "bank_import_rows.user_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "bank_number IS NULL OR bank_number > 0", name="ck_loan_schedule_membership_bank_number"
        ),
        CheckConstraint(
            "(bank_number IS NULL) = (source_row_id IS NULL)",
            name="ck_loan_schedule_membership_provenance",
        ),
        CheckConstraint(
            "principal_pln >= 0 AND interest_pln >= 0 AND fees_pln >= 0",
            name="ck_loan_schedule_membership_components",
        ),
        CheckConstraint(
            "principal_pln + interest_pln + fees_pln BETWEEN 1 AND 9007199254740991",
            name="ck_loan_schedule_membership_total",
        ),
        CheckConstraint(
            "balance_after_pln IS NULL OR balance_after_pln BETWEEN 0 AND 9007199254740991",
            name="ck_loan_schedule_membership_balance",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    loan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    installment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    bank_number: Mapped[int | None] = mapped_column(Integer)
    source_row_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    due_date: Mapped[date] = mapped_column(Date)
    principal_pln: Mapped[int] = mapped_column(BigInteger)
    interest_pln: Mapped[int] = mapped_column(BigInteger)
    fees_pln: Mapped[int] = mapped_column(BigInteger)
    balance_after_pln: Mapped[int | None] = mapped_column(BigInteger)
