"""Consent, generation and review evidence; never a mirrored monetary ledger."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CategorizationSuggestionSettings(Base):
    __tablename__ = "categorization_suggestion_settings"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_suggestion_settings_version"),
        CheckConstraint(
            "NOT enabled OR (consent_at IS NOT NULL AND accepted_server_epoch IS NOT NULL AND accepted_server_epoch > 0 AND accepted_configuration_fingerprint IS NOT NULL)",
            name="ck_suggestion_consent",
        ),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    version: Mapped[int] = mapped_column(default=1)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_server_epoch: Mapped[int | None]
    accepted_configuration_fingerprint: Mapped[str | None] = mapped_column(String(64))


class CategorizationLlmPolicy(Base):
    __tablename__ = "categorization_llm_policy"
    __table_args__ = (
        CheckConstraint("id = 1 AND epoch > 0", name="ck_suggestion_policy_singleton"),
        CheckConstraint(
            "NOT enabled OR configuration_fingerprint IS NOT NULL",
            name="ck_suggestion_policy_config",
        ),
    )
    # Singleton intentionally replaces Base's UUID key, as DocumentVisionPolicy does.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)  # type: ignore[assignment]
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    epoch: Mapped[int] = mapped_column(default=1)
    configuration_fingerprint: Mapped[str | None] = mapped_column(String(64))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CategorizationSuggestionJob(Base):
    __tablename__ = "categorization_suggestion_jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "transaction_id", name="uq_suggestion_creation"),
        CheckConstraint(
            "status IN ('ready','preparing','reserved','dispatching','completed','cancelled','failed','uncertain')",
            name="ck_suggestion_job_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_suggestion_job_attempts"),
        Index("ix_suggestion_job_dispatch", "status", "next_attempt_at"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    source_context_sha256: Mapped[str] = mapped_column(String(64))
    marker_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    settings_version: Mapped[int]
    user_epoch: Mapped[int]
    server_epoch: Mapped[int]
    configuration_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="ready")
    attempts: Mapped[int] = mapped_column(default=0)
    lease_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    lease_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatch_nonce: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    packet_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    private_key_map: Mapped[dict[str, str] | None] = mapped_column(JSONB)
    taxonomy_sha256: Mapped[str | None] = mapped_column(String(64))
    request_sha256: Mapped[str | None] = mapped_column(String(64))
    result_kind: Mapped[str | None] = mapped_column(String(24))
    reason_code: Mapped[str | None] = mapped_column(String(64))


class CategorizationLlmUsageReservation(Base):
    __tablename__ = "categorization_llm_usage_reservations"
    __table_args__ = (
        CheckConstraint(
            "state IN ('reserved','dispatching','known','unknown','released')",
            name="ck_suggestion_usage_state",
        ),
        CheckConstraint("reservation_version > 0", name="ck_suggestion_usage_version"),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0", name="ck_suggestion_usage_input"
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0", name="ck_suggestion_usage_output"
        ),
        Index("ix_suggestion_usage_quota", "user_id", "usage_date", "state"),
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categorization_suggestion_jobs.id", ondelete="RESTRICT"), unique=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    usage_date: Mapped[date] = mapped_column(Date)
    reservation_version: Mapped[int] = mapped_column(default=1)
    held_by_lease_token: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    state: Mapped[str] = mapped_column(String(16), default="reserved")
    dispatch_nonce: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    configuration_fingerprint: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    response_id_hash: Mapped[str | None] = mapped_column(String(64))


class CategorizationProposalItem(Base):
    __tablename__ = "categorization_proposal_items"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_proposal_version"),
        CheckConstraint(
            "status IN ('pending','approved','rejected','stale','expired','superseded')",
            name="ck_proposal_status",
        ),
        CheckConstraint("confidence IN ('low','medium','high')", name="ck_proposal_confidence"),
        CheckConstraint(
            "(decision = 'existing_category' AND target_category_id IS NOT NULL AND new_category IS NULL) OR (decision = 'new_category' AND target_category_id IS NULL AND new_category IS NOT NULL)",
            name="ck_proposal_target",
        ),
        CheckConstraint(
            "status != 'approved' OR approval_receipt_id IS NOT NULL", name="ck_proposal_approval"
        ),
        Index("ix_proposal_queue", "user_id", "status", "created_at", "id"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categorization_suggestion_jobs.id", ondelete="RESTRICT"), unique=True
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("financial_transactions.id", ondelete="SET NULL")
    )
    source_context_sha256: Mapped[str] = mapped_column(String(64))
    request_sha256: Mapped[str] = mapped_column(String(64))
    taxonomy_sha256: Mapped[str] = mapped_column(String(64))
    generated_description: Mapped[str] = mapped_column(String(2000))
    private_key_map: Mapped[dict[str, str]] = mapped_column(JSONB)
    decision: Mapped[str] = mapped_column(String(24))
    explanation: Mapped[str] = mapped_column(String(2000))
    confidence: Mapped[str] = mapped_column(String(8))
    new_category: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    target_category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT")
    )
    version: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approval_receipt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("finance_command_receipts.id", ondelete="RESTRICT")
    )
