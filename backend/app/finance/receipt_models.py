"""Append-only human product evidence; mutable heads never mirror ledger amounts."""

import uuid
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ReceiptStore(Base):
    __tablename__ = "receipt_stores"
    __table_args__ = (
        UniqueConstraint("user_id", "normalized_name", name="uq_receipt_store_name"),
        UniqueConstraint("user_id", "id", name="uq_receipt_store_owner"),
        CheckConstraint("version > 0", name="ck_receipt_store_version"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    name: Mapped[str] = mapped_column(String(500))
    normalized_name: Mapped[str] = mapped_column(String(500))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    version: Mapped[int] = mapped_column(default=1)


class ReceiptItemState(Base):
    __tablename__ = "receipt_item_states"
    __table_args__ = (
        UniqueConstraint("user_id", "bill_id", name="uq_receipt_state_bill"),
        CheckConstraint("version > 0", name="ck_receipt_state_version"),
        ForeignKeyConstraint(
            ["user_id", "bill_id", "current_draft_revision_id"],
            [
                "receipt_item_revisions.user_id",
                "receipt_item_revisions.bill_id",
                "receipt_item_revisions.id",
            ],
            ondelete="RESTRICT",
            name="fk_receipt_state_draft",
        ),
        ForeignKeyConstraint(
            ["user_id", "bill_id", "current_approved_revision_id"],
            [
                "receipt_item_revisions.user_id",
                "receipt_item_revisions.bill_id",
                "receipt_item_revisions.id",
            ],
            ondelete="RESTRICT",
            name="fk_receipt_state_approved",
        ),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    bill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("financial_documents.id", ondelete="RESTRICT")
    )
    version: Mapped[int] = mapped_column(default=1)
    current_draft_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    current_approved_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    last_apply_receipt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("finance_command_receipts.id", ondelete="RESTRICT")
    )


class ReceiptItemRevision(Base):
    __tablename__ = "receipt_item_revisions"
    __table_args__ = (
        UniqueConstraint("user_id", "id", name="uq_receipt_revision_owner"),
        UniqueConstraint("user_id", "bill_id", "id", name="uq_receipt_revision_bill"),
        UniqueConstraint("user_id", "bill_id", "sequence", name="uq_receipt_revision_sequence"),
        ForeignKeyConstraint(
            ["user_id", "store_id"],
            ["receipt_stores.user_id", "receipt_stores.id"],
            ondelete="RESTRICT",
            name="fk_receipt_revision_store",
        ),
        ForeignKeyConstraint(
            ["user_id", "bill_id", "parent_revision_id"],
            [
                "receipt_item_revisions.user_id",
                "receipt_item_revisions.bill_id",
                "receipt_item_revisions.id",
            ],
            ondelete="RESTRICT",
            name="fk_receipt_revision_parent",
        ),
        CheckConstraint(
            "kind IN ('draft','approved') AND sequence > 0", name="ck_receipt_revision_kind"
        ),
        CheckConstraint(
            "kind != 'approved' OR (store_id IS NOT NULL AND store_version IS NOT NULL AND store_version > 0)",
            name="ck_receipt_revision_approved",
        ),
        Index("ix_receipt_revision_store", "user_id", "store_id", "kind"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    bill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("financial_documents.id", ondelete="RESTRICT")
    )
    sequence: Mapped[int]
    kind: Mapped[str] = mapped_column(String(8))
    store_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    store_version: Mapped[int | None]
    header_sha256: Mapped[str] = mapped_column(String(64))
    header_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    body_sha256: Mapped[str] = mapped_column(String(64))
    parent_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    command_receipt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("finance_command_receipts.id", ondelete="RESTRICT")
    )


class ReceiptItemLine(Base):
    __tablename__ = "receipt_item_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "revision_id"],
            ["receipt_item_revisions.user_id", "receipt_item_revisions.id"],
            ondelete="RESTRICT",
            name="fk_receipt_line_revision",
        ),
        UniqueConstraint("user_id", "revision_id", "line_key", name="uq_receipt_line_key"),
        UniqueConstraint("revision_id", "position", name="uq_receipt_line_position"),
        CheckConstraint("position >= 0", name="ck_receipt_line_position"),
        CheckConstraint(
            "amount_minor IS NULL OR amount_minor BETWEEN 0 AND 9007199254740991",
            name="ck_receipt_line_amount",
        ),
        Index("ix_receipt_line_history", "user_id", "normalized_name", "revision_id"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    line_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    position: Mapped[int]
    name: Mapped[str] = mapped_column(String(2000))
    normalized_name: Mapped[str] = mapped_column(String(2000))
    amount_minor: Mapped[int | None] = mapped_column(BigInteger)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT")
    )
    hint_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    category_path_sha256: Mapped[str | None] = mapped_column(String(64))


class ReceiptItemDiscount(Base):
    __tablename__ = "receipt_item_discounts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "revision_id"],
            ["receipt_item_revisions.user_id", "receipt_item_revisions.id"],
            ondelete="RESTRICT",
            name="fk_receipt_discount_revision",
        ),
        UniqueConstraint("user_id", "revision_id", "discount_key", name="uq_receipt_discount_key"),
        UniqueConstraint("revision_id", "position", name="uq_receipt_discount_position"),
        CheckConstraint("position >= 0", name="ck_receipt_discount_position"),
        CheckConstraint(
            "amount_minor IS NULL OR amount_minor BETWEEN 1 AND 9007199254740991",
            name="ck_receipt_discount_amount",
        ),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    discount_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    position: Mapped[int]
    name: Mapped[str] = mapped_column(String(2000))
    amount_minor: Mapped[int | None] = mapped_column(BigInteger)


class ReceiptItemDiscountShare(Base):
    __tablename__ = "receipt_item_discount_shares"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "revision_id", "line_key"],
            [
                "receipt_item_lines.user_id",
                "receipt_item_lines.revision_id",
                "receipt_item_lines.line_key",
            ],
            ondelete="RESTRICT",
            name="fk_receipt_share_line",
        ),
        ForeignKeyConstraint(
            ["user_id", "revision_id", "discount_key"],
            [
                "receipt_item_discounts.user_id",
                "receipt_item_discounts.revision_id",
                "receipt_item_discounts.discount_key",
            ],
            ondelete="RESTRICT",
            name="fk_receipt_share_discount",
        ),
        UniqueConstraint(
            "user_id", "revision_id", "discount_key", "line_key", name="uq_receipt_discount_share"
        ),
        CheckConstraint(
            "amount_minor IS NULL OR amount_minor BETWEEN 1 AND 9007199254740991",
            name="ck_receipt_share_amount",
        ),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    discount_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    line_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    amount_minor: Mapped[int | None] = mapped_column(BigInteger)
