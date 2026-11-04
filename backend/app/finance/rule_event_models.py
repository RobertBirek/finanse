"""Durable creation-only delivery. Observed rule references confer no authority."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TransactionRuleEvent(Base):
    __tablename__ = "transaction_rule_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ready','processing','applied','skipped','failed')",
            name="ck_rule_event_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_rule_event_attempts"),
        CheckConstraint(
            "status != 'processing' OR (lease_token IS NOT NULL AND lease_deadline IS NOT NULL)",
            name="ck_rule_event_lease",
        ),
        Index("ix_rule_event_dispatch", "status", "next_attempt_at", "lease_deadline"),
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("financial_transactions.id", ondelete="CASCADE"), unique=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    settings_version: Mapped[int]
    observed_rule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    observed_rule_version: Mapped[int | None]
    source_context_sha256: Mapped[str] = mapped_column(String(64))
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    status: Mapped[str] = mapped_column(String(16))
    reason_code: Mapped[str | None] = mapped_column(String(40))
    attempts: Mapped[int] = mapped_column(default=0)
    lease_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    lease_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    result_receipt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("finance_command_receipts.id", ondelete="RESTRICT")
    )
