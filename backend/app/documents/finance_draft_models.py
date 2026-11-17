"""A new-upload intent is durable even when Redis or financial registration is down."""

import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DocumentFinanceDraftIntent(Base):
    __tablename__ = "document_finance_draft_intents"
    __table_args__ = (
        UniqueConstraint("document_id", name="uq_document_finance_draft_document"),
        ForeignKeyConstraint(
            ["document_id", "user_id"],
            ["documents.id", "documents.user_id"],
            name="fk_document_finance_draft_owner",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "state IN ('pending', 'needs_review', 'failed', 'succeeded')",
            name="ck_document_finance_draft_state",
        ),
        Index("ix_document_finance_draft_state", "state", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_extraction_revisions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    bill_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_documents.id", ondelete="RESTRICT"), nullable=True
    )
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
