"""Descriptive overlays are independent of source descriptions and ledger postings."""

import uuid

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TransactionAnnotation(Base):
    __tablename__ = "transaction_annotations"
    __table_args__ = (
        UniqueConstraint("transaction_id", name="uq_transaction_annotation_transaction"),
        ForeignKeyConstraint(
            ["transaction_id", "user_id"],
            ["financial_transactions.id", "financial_transactions.user_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("version > 0", name="ck_transaction_annotation_version"),
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    display_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)


class FinanceTag(Base):
    __tablename__ = "finance_tags"
    __table_args__ = (
        UniqueConstraint("user_id", "normalized_name", name="uq_finance_tag_owner_name"),
        UniqueConstraint("id", "user_id", name="uq_finance_tag_id_owner"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False)


class TransactionTag(Base):
    __tablename__ = "transaction_tags"
    __table_args__ = (
        UniqueConstraint("transaction_id", "tag_id", name="uq_transaction_tag_link"),
        ForeignKeyConstraint(
            ["transaction_id", "user_id"],
            ["financial_transactions.id", "financial_transactions.user_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tag_id", "user_id"], ["finance_tags.id", "finance_tags.user_id"], ondelete="CASCADE"
        ),
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tag_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tag: Mapped[FinanceTag] = relationship(lazy="selectin", viewonly=True)
