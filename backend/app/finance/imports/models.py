"""Durable source preparation and review; staging has no ledger side effects."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ImportOwned(Base):
    __abstract__ = True

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )


class ImportBatch(ImportOwned):
    __tablename__ = "bank_import_batches"
    __table_args__ = (
        UniqueConstraint("id", "user_id", "kind", name="uq_bank_import_batch_owner_kind"),
        UniqueConstraint("id", "user_id", name="uq_bank_import_batch_owner"),
        CheckConstraint("kind IN ('statement','loan_schedule')", name="ck_bank_import_kind"),
        CheckConstraint("version >= 1", name="ck_bank_import_batch_version"),
        CheckConstraint(
            "commit_state IN ('not_committed','partial','committed')",
            name="ck_bank_import_commit_state",
        ),
    )

    kind: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    commit_state: Mapped[str] = mapped_column(
        String(20), default="not_committed", server_default="not_committed"
    )


class ImportSource(ImportOwned):
    __tablename__ = "bank_import_sources"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "document_id", "kind", name="uq_bank_import_source_document_kind"
        ),
        UniqueConstraint("id", "user_id", "batch_id", name="uq_bank_import_source_owner_batch"),
        ForeignKeyConstraint(
            ["batch_id", "user_id", "kind"],
            ["bank_import_batches.id", "bank_import_batches.user_id", "bank_import_batches.kind"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["document_id", "user_id"], ["documents.id", "documents.user_id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["current_revision_id", "user_id", "id"],
            [
                "bank_import_revisions.id",
                "bank_import_revisions.user_id",
                "bank_import_revisions.source_id",
            ],
            name="fk_bank_import_current_revision",
            use_alter=True,
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "bank IS NULL OR bank IN ('velo','ing','revolut')", name="ck_bank_import_source_bank"
        ),
        CheckConstraint(
            "processing_state IN ('queued','processing','ready','error','unsupported')",
            name="ck_bank_import_processing_state",
        ),
        CheckConstraint(
            "validation_state IN ('passed','needs_review','blocked')",
            name="ck_bank_import_validation_state",
        ),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(String(20))
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    bank: Mapped[str | None] = mapped_column(String(20))
    layout: Mapped[str | None] = mapped_column(String(100))
    parser_version: Mapped[str | None] = mapped_column(String(100))
    account_reference: Mapped[str | None] = mapped_column(String(200))
    currency: Mapped[str | None] = mapped_column(String(3))
    processing_state: Mapped[str] = mapped_column(
        String(20), default="queued", server_default="queued"
    )
    validation_state: Mapped[str] = mapped_column(
        String(20), default="needs_review", server_default="needs_review"
    )


class ImportRevision(ImportOwned):
    __tablename__ = "bank_import_revisions"
    __table_args__ = (
        UniqueConstraint("source_id", "number", name="uq_bank_import_revision_number"),
        UniqueConstraint("id", "user_id", "source_id", name="uq_bank_import_revision_owner_source"),
        UniqueConstraint("id", "user_id", "batch_id", name="uq_bank_import_revision_owner_batch"),
        ForeignKeyConstraint(
            ["source_id", "user_id", "batch_id"],
            [
                "bank_import_sources.id",
                "bank_import_sources.user_id",
                "bank_import_sources.batch_id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("number >= 1", name="ck_bank_import_revision_number"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    number: Mapped[int] = mapped_column(Integer)
    source_sha256: Mapped[str] = mapped_column(String(64))
    parser_version: Mapped[str | None] = mapped_column(String(100))
    result: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    checks: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    error_code: Mapped[str | None] = mapped_column(String(100))


class ImportRow(ImportOwned):
    __tablename__ = "bank_import_rows"
    __table_args__ = (
        UniqueConstraint("revision_id", "ordinal", name="uq_bank_import_row_ordinal"),
        UniqueConstraint("revision_id", "source_key", name="uq_bank_import_row_key"),
        UniqueConstraint("id", "user_id", "batch_id", name="uq_bank_import_row_owner_batch"),
        ForeignKeyConstraint(
            ["revision_id", "user_id", "source_id"],
            [
                "bank_import_revisions.id",
                "bank_import_revisions.user_id",
                "bank_import_revisions.source_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_id", "user_id", "batch_id"],
            [
                "bank_import_sources.id",
                "bank_import_sources.user_id",
                "bank_import_sources.batch_id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("ordinal >= 1", name="ck_bank_import_row_ordinal"),
        CheckConstraint("kind IN ('statement','loan_schedule')", name="ck_bank_import_row_kind"),
    )

    revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    ordinal: Mapped[int] = mapped_column(Integer)
    source_key: Mapped[str] = mapped_column(String(255))
    row_hash: Mapped[str] = mapped_column(String(64), index=True)
    fields: Mapped[dict[str, object]] = mapped_column(JSONB)


class ImportJob(ImportOwned):
    __tablename__ = "bank_import_jobs"
    __table_args__ = (
        UniqueConstraint("revision_id", name="uq_bank_import_job_revision"),
        ForeignKeyConstraint(
            ["revision_id", "user_id", "source_id"],
            [
                "bank_import_revisions.id",
                "bank_import_revisions.user_id",
                "bank_import_revisions.source_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_id", "user_id", "batch_id"],
            [
                "bank_import_sources.id",
                "bank_import_sources.user_id",
                "bank_import_sources.batch_id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "state IN ('queued','processing','ready','error','unsupported')",
            name="ck_bank_import_job_state",
        ),
        CheckConstraint("attempt >= 0", name="ck_bank_import_job_attempt"),
        Index("ix_bank_import_job_dispatch", "state", "next_attempt_at"),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    state: Mapped[str] = mapped_column(String(20), default="queued", server_default="queued")
    attempt: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    lease_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))


class ImportGroup(ImportOwned):
    __tablename__ = "bank_import_groups"
    __table_args__ = (
        UniqueConstraint("id", "user_id", "batch_id", name="uq_bank_import_group_owner_batch"),
        ForeignKeyConstraint(
            ["batch_id", "user_id"],
            ["bank_import_batches.id", "bank_import_batches.user_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("version >= 1", name="ck_bank_import_group_version"),
        CheckConstraint(
            "state IN ('draft','ready','committed','deferred')", name="ck_bank_import_group_state"
        ),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    state: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft")


class ImportGroupRow(ImportOwned):
    __tablename__ = "bank_import_group_rows"
    __table_args__ = (
        UniqueConstraint("row_id", name="uq_bank_import_consumed_row"),
        ForeignKeyConstraint(
            ["group_id", "user_id", "batch_id"],
            ["bank_import_groups.id", "bank_import_groups.user_id", "bank_import_groups.batch_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["row_id", "user_id", "batch_id"],
            ["bank_import_rows.id", "bank_import_rows.user_id", "bank_import_rows.batch_id"],
            ondelete="RESTRICT",
        ),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    row_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))


class ImportDecision(ImportOwned):
    __tablename__ = "bank_import_decisions"
    __table_args__ = (
        UniqueConstraint("group_id", "version", name="uq_bank_import_decision_version"),
        ForeignKeyConstraint(
            ["group_id", "user_id", "batch_id"],
            ["bank_import_groups.id", "bank_import_groups.user_id", "bank_import_groups.batch_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("version >= 1", name="ck_bank_import_decision_version"),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict[str, object]] = mapped_column(JSONB)


class ImportPreview(ImportOwned):
    __tablename__ = "bank_import_previews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["batch_id", "user_id"],
            ["bank_import_batches.id", "bank_import_batches.user_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("version >= 1", name="ck_bank_import_preview_version"),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    version: Mapped[int] = mapped_column(Integer)
    request_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)


class ImportEvidence(ImportOwned):
    __tablename__ = "bank_import_evidence"
    __table_args__ = (
        UniqueConstraint("row_id", "component", name="uq_bank_import_evidence_component"),
        ForeignKeyConstraint(
            ["row_id", "user_id", "batch_id"],
            ["bank_import_rows.id", "bank_import_rows.user_id", "bank_import_rows.batch_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["group_id", "user_id", "batch_id"],
            ["bank_import_groups.id", "bank_import_groups.user_id", "bank_import_groups.batch_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "component IN ('main','fee','whole')", name="ck_bank_import_evidence_component"
        ),
        CheckConstraint("attributed_source_amount <> 0", name="ck_bank_import_evidence_nonzero"),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    row_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_transactions.id", ondelete="RESTRICT"), index=True
    )
    posting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("postings.id", ondelete="RESTRICT")
    )
    receipt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finance_command_receipts.id", ondelete="RESTRICT")
    )
    component: Mapped[str] = mapped_column(String(10))
    attributed_source_amount: Mapped[int] = mapped_column(BigInteger)


class ImportBankIdentity(ImportOwned):
    __tablename__ = "bank_import_identities"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "bank",
            "account_id",
            "currency",
            "strong_reference",
            name="uq_bank_import_strong_identity",
        ),
        ForeignKeyConstraint(
            ["group_id", "user_id", "batch_id"],
            ["bank_import_groups.id", "bank_import_groups.user_id", "bank_import_groups.batch_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("bank IN ('velo','ing','revolut')", name="ck_bank_import_identity_bank"),
        CheckConstraint("currency IN ('PLN','EUR','USD')", name="ck_bank_import_identity_currency"),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    bank: Mapped[str] = mapped_column(String(20))
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT")
    )
    currency: Mapped[str] = mapped_column(String(3))
    strong_reference: Mapped[str] = mapped_column(String(255))
