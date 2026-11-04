"""Explicit future-only categorization authority; no mirrored financial amounts."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.finance import suggestion_models as _suggestion_models  # noqa: F401


class TransactionCategorizationSettings(Base):
    __tablename__ = "transaction_categorization_settings"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_rule_settings_version"),
        CheckConstraint(
            "NOT rules_enabled OR uncategorized_category_id IS NOT NULL",
            name="ck_rule_settings_marker",
        ),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    uncategorized_category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT")
    )
    rules_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    version: Mapped[int] = mapped_column(default=1)


class TransactionCategorizationRule(Base):
    __tablename__ = "transaction_categorization_rules"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_rule_version"),
        CheckConstraint("state IN ('draft','active','paused','retired')", name="ck_rule_state"),
        CheckConstraint(
            "state != 'active' OR (approved_version IS NOT NULL AND approved_version = version AND approval_receipt_id IS NOT NULL AND approved_for_uncategorized_category_id IS NOT NULL AND approved_target_sha256 IS NOT NULL)",
            name="ck_rule_active_grant",
        ),
        Index(
            "uq_rule_active_pattern",
            "user_id",
            "normalized_description_exact",
            unique=True,
            postgresql_where=text("state = 'active'"),
        ),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    display_description: Mapped[str] = mapped_column(String(2000))
    normalized_description_exact: Mapped[str] = mapped_column(String(2000))
    target_category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT")
    )
    state: Mapped[str] = mapped_column(String(16), default="draft")
    version: Mapped[int] = mapped_column(default=1)
    approved_version: Mapped[int | None]
    approved_for_uncategorized_category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT")
    )
    approved_target_sha256: Mapped[str | None] = mapped_column(String(64))
    approval_receipt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("finance_command_receipts.id", ondelete="RESTRICT")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TransactionCategorizationOrigin(Base):
    __tablename__ = "transaction_categorization_origins"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_rule_origin_version"),
        CheckConstraint(
            "origin IN ('manual','approved_rule','approved_llm')", name="ck_rule_origin_kind"
        ),
        CheckConstraint(
            "origin != 'approved_rule' OR (rule_id IS NOT NULL AND rule_version IS NOT NULL AND approval_receipt_id IS NOT NULL AND approval_snapshot_sha256 IS NOT NULL)",
            name="ck_rule_origin_grant",
        ),
        CheckConstraint(
            "(origin = 'approved_llm' AND proposal_item_id IS NOT NULL AND approval_receipt_id IS NOT NULL AND approval_snapshot_sha256 IS NOT NULL AND rule_id IS NULL AND rule_version IS NULL) OR (origin != 'approved_llm' AND proposal_item_id IS NULL)",
            name="ck_rule_origin_proposal_grant",
        ),
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("financial_transactions.id", ondelete="CASCADE"), unique=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    origin: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(default=1)
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("transaction_categorization_rules.id", ondelete="RESTRICT")
    )
    rule_version: Mapped[int | None]
    approval_receipt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("finance_command_receipts.id", ondelete="RESTRICT")
    )
    approval_snapshot_sha256: Mapped[str | None] = mapped_column(String(64))
    assignment_sha256: Mapped[str] = mapped_column(String(64))
    proposal_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categorization_proposal_items.id", ondelete="RESTRICT")
    )
