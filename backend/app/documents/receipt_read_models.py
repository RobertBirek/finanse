"""Purpose-specific receipt image work; old header jobs/revisions remain untouched."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ReceiptReadPolicy(Base):
    __tablename__ = "receipt_read_policy"
    __table_args__ = (CheckConstraint("id = 1 AND epoch > 0", name="ck_read_policy_singleton"),)
    id: Mapped[int] = mapped_column(primary_key=True, default=1)  # type: ignore[assignment]
    enabled: Mapped[bool] = mapped_column(default=False, server_default="false")
    epoch: Mapped[int] = mapped_column(default=1, server_default="1")
    configuration_fingerprint: Mapped[str | None] = mapped_column(String(64))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReceiptReadStream(Base):
    __tablename__ = "receipt_read_streams"
    __table_args__ = (
        UniqueConstraint("user_id", "id", name="uq_read_stream_owner"),
        UniqueConstraint(
            "user_id",
            "bill_id",
            "source_sha256",
            "configuration_fingerprint",
            name="uq_read_stream_content",
        ),
        ForeignKeyConstraint(
            ["user_id", "id", "latest_job_id"],
            ["receipt_read_jobs.user_id", "receipt_read_jobs.stream_id", "receipt_read_jobs.id"],
            ondelete="RESTRICT",
            name="fk_read_stream_head",
            use_alter=True,
        ),
        CheckConstraint("version > 0", name="ck_read_stream_version"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    bill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("financial_documents.id", ondelete="RESTRICT")
    )
    source_sha256: Mapped[str] = mapped_column(String(64))
    configuration_fingerprint: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    latest_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class ReceiptReadJob(Base):
    __tablename__ = "receipt_read_jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "id", name="uq_read_job_owner"),
        UniqueConstraint("user_id", "stream_id", "id", name="uq_read_job_stream"),
        UniqueConstraint("stream_id", "generation", name="uq_read_generation"),
        ForeignKeyConstraint(
            ["user_id", "stream_id"],
            ["receipt_read_streams.user_id", "receipt_read_streams.id"],
            ondelete="RESTRICT",
            name="fk_read_job_stream",
        ),
        CheckConstraint(
            "state IN ('pending','preparing','dispatched','succeeded','failed','unknown','paused','cancelled','superseded')",
            name="ck_read_job_state",
        ),
        CheckConstraint(
            "version > 0 AND generation > 0 AND prepare_attempts >= 0", name="ck_read_job_versions"
        ),
        CheckConstraint(
            "(dispatch_token IS NULL) = (dispatched_at IS NULL)", name="ck_read_job_marker_pair"
        ),
        CheckConstraint(
            "state NOT IN ('dispatched','unknown') OR dispatch_token IS NOT NULL",
            name="ck_read_job_marker_required",
        ),
        CheckConstraint(
            "dispatch_token IS NULL OR state NOT IN ('pending','preparing','cancelled')",
            name="ck_read_job_no_resend",
        ),
        Index("ix_read_jobs_dispatch", "state", "next_attempt_at"),
        Index("ix_read_jobs_history", "user_id", "bill_id", "created_at", "id"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    stream_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    bill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("financial_documents.id", ondelete="RESTRICT")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="RESTRICT"))
    generation: Mapped[int]
    source_sha256: Mapped[str] = mapped_column(String(64))
    header_sha256: Mapped[str] = mapped_column(String(64))
    configuration_fingerprint: Mapped[str] = mapped_column(String(64))
    policy_epoch: Mapped[int]
    consent_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    grant_receipt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("finance_command_receipts.id", ondelete="RESTRICT")
    )
    state: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    prepare_attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatch_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))


class ReceiptReadExtraction(Base):
    __tablename__ = "receipt_read_extractions"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_read_extraction_job"),
        UniqueConstraint("user_id", "id", name="uq_read_extraction_owner"),
        UniqueConstraint("user_id", "job_id", "id", name="uq_read_extraction_owner_job"),
        ForeignKeyConstraint(
            ["user_id", "job_id"],
            ["receipt_read_jobs.user_id", "receipt_read_jobs.id"],
            ondelete="RESTRICT",
            name="fk_read_extraction_job",
        ),
        CheckConstraint(
            "quality IN ('complete','partial','unsupported')", name="ck_read_extraction_quality"
        ),
        CheckConstraint(
            "(input_tokens IS NULL OR input_tokens >= 0) AND (output_tokens IS NULL OR output_tokens >= 0)",
            name="ck_read_extraction_tokens",
        ),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    bill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("financial_documents.id", ondelete="RESTRICT")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="RESTRICT"))
    source_sha256: Mapped[str] = mapped_column(String(64))
    derivative_sha256: Mapped[str] = mapped_column(String(64))
    header_sha256: Mapped[str] = mapped_column(String(64))
    payload_sha256: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    proposal_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    problems_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    quality: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(100))
    schema_version: Mapped[str] = mapped_column(String(100))
    normalizer_version: Mapped[str] = mapped_column(String(100))
    configuration_fingerprint: Mapped[str] = mapped_column(String(64))
    policy_epoch: Mapped[int]
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]


class ReceiptReadUsage(Base):
    __tablename__ = "receipt_read_usage"
    __table_args__ = (
        UniqueConstraint("scope_key", "usage_date", name="uq_read_usage_scope_date"),
        CheckConstraint("reserved_calls >= 0", name="ck_read_usage_calls"),
    )
    scope_key: Mapped[str] = mapped_column(String(64))
    usage_date: Mapped[date]
    reserved_calls: Mapped[int] = mapped_column(default=0, server_default="0")


class ReceiptReadReservation(Base):
    __tablename__ = "receipt_read_reservations"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_read_reservation_job"),
        UniqueConstraint("dispatch_token", name="uq_read_reservation_token"),
        ForeignKeyConstraint(
            ["user_id", "job_id"],
            ["receipt_read_jobs.user_id", "receipt_read_jobs.id"],
            ondelete="RESTRICT",
            name="fk_read_reservation_job",
        ),
        CheckConstraint(
            "outcome IN ('unknown','success','error')", name="ck_read_reservation_outcome"
        ),
        CheckConstraint(
            "image_pixels > 0 AND image_bytes > 0 AND output_token_limit > 0 AND response_byte_limit > 0",
            name="ck_read_reservation_limits",
        ),
        CheckConstraint(
            "(input_tokens IS NULL OR input_tokens >= 0) AND (output_tokens IS NULL OR output_tokens >= 0)",
            name="ck_read_reservation_tokens",
        ),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    dispatch_token: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    usage_date: Mapped[date]
    image_pixels: Mapped[int]
    image_bytes: Mapped[int]
    output_token_limit: Mapped[int]
    response_byte_limit: Mapped[int]
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    outcome: Mapped[str] = mapped_column(String(8), default="unknown", server_default="unknown")
