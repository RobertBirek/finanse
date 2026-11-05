"""Immutable extraction lineage for each financial human revision, not a second ledger."""

import uuid
from typing import Any

from sqlalchemy import ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ReceiptReadLineage(Base):
    __tablename__ = "receipt_read_lineage"
    __table_args__ = (
        UniqueConstraint("item_revision_id", name="uq_read_lineage_revision"),
        ForeignKeyConstraint(
            ["user_id", "bill_id", "item_revision_id"],
            [
                "receipt_item_revisions.user_id",
                "receipt_item_revisions.bill_id",
                "receipt_item_revisions.id",
            ],
            ondelete="RESTRICT",
            name="fk_read_lineage_revision",
        ),
        ForeignKeyConstraint(
            ["user_id", "extraction_id"],
            ["receipt_read_extractions.user_id", "receipt_read_extractions.id"],
            ondelete="RESTRICT",
            name="fk_read_lineage_extraction",
        ),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    bill_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    item_revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    extraction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    extraction_sha256: Mapped[str] = mapped_column(String(64))
    body_sha256: Mapped[str] = mapped_column(String(64))
    line_map: Mapped[dict[str, Any]] = mapped_column(JSONB)
    discount_map: Mapped[dict[str, Any]] = mapped_column(JSONB)
    pending_problem_keys: Mapped[list[str]] = mapped_column(JSONB)
    acknowledgements: Mapped[dict[str, str]] = mapped_column(JSONB)
