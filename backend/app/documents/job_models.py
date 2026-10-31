import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.documents import models as _document_models  # noqa: F401 - register referenced metadata


class DocumentProcessingJob(Base):
    __tablename__ = "document_processing_jobs"
    __table_args__ = (
        CheckConstraint("kind IN ('vision', 'local_ocr')", name="ck_document_processing_job_kind"),
        CheckConstraint(
            "state IN ('pending', 'processing', 'succeeded', 'failed', 'paused', 'superseded')",
            name="ck_document_processing_job_state",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_document_processing_job_attempt_count"),
        UniqueConstraint("user_id", "kind", "intent_key", name="uq_document_processing_job_intent"),
        UniqueConstraint("revision_id", name="uq_document_processing_job_revision"),
        Index("ix_document_processing_jobs_state_next_attempt_at", "state", "next_attempt_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_extraction_revisions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    intent_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending", default="pending"
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    call_reserved_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    policy_epoch: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)


class DocumentVisionUsage(Base):
    __tablename__ = "document_vision_usage"
    __table_args__ = (
        CheckConstraint("reserved_calls >= 0", name="ck_document_vision_usage_reserved_calls"),
        UniqueConstraint("user_id", "usage_date", name="uq_document_vision_usage_user_date"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    usage_date: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=func.current_date()
    )
    reserved_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )


class DocumentVisionPolicy(Base):
    __tablename__ = "document_vision_policy"
    __table_args__ = (CheckConstraint("id = 1", name="ck_document_vision_policy_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)  # type: ignore[assignment]
    enabled: Mapped[bool] = mapped_column(nullable=False, server_default="false", default=False)
    epoch: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1", default=1)
    configuration_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
