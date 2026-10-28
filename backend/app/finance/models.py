import uuid
from datetime import date

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Account(Base):
    __tablename__ = "accounts"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="PLN")
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_budget_account: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    opened_at: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=func.current_date()
    )
    closed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    account_holder: Mapped[str | None] = mapped_column(String(200), nullable=True)
    iban: Mapped[str | None] = mapped_column(String(34), nullable=True)
    bic: Mapped[str | None] = mapped_column(String(11), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    postings: Mapped[list["Posting"]] = relationship(
        "Posting", back_populates="account", cascade="all, delete-orphan"
    )

    @property
    def balance_pln(self) -> int:
        return getattr(self, "_balance", 0)

    @property
    def balance_source(self) -> int:
        return getattr(self, "_balance_source", 0)

    @property
    def can_change_currency(self) -> bool:
        return getattr(self, "_can_change_currency", False)

    @can_change_currency.setter
    def can_change_currency(self, value: bool) -> None:
        self._can_change_currency = value


class Category(Base):
    __tablename__ = "categories"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    parent: Mapped["Category | None"] = relationship(
        "Category", remote_side="Category.id", backref="children"
    )
    postings: Mapped[list["Posting"]] = relationship("Posting", back_populates="category")


class FinanceSettings(Base):
    __tablename__ = "finance_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    payday_day: Mapped[int] = mapped_column(nullable=False, default=10)
    payday_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    forecast_horizon_days: Mapped[int] = mapped_column(nullable=False, default=30)
    overdue_grace_days: Mapped[int] = mapped_column(nullable=False, default=3)


class ScheduledFinanceItem(Base):
    __tablename__ = "scheduled_finance_items"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    cadence: Mapped[str] = mapped_column(String(20), nullable=False, default="monthly")
    due_day: Mapped[int] = mapped_column(nullable=False)
    amount_method: Mapped[str] = mapped_column(String(20), nullable=False)
    fixed_amount_pln: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    account: Mapped["Account"] = relationship("Account")
    category: Mapped["Category"] = relationship("Category")


class CategoryBudget(Base):
    __tablename__ = "category_budgets"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    amount_pln: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (
        CheckConstraint("amount_pln > 0", name="ck_category_budget_amount"),
        UniqueConstraint("user_id", "category_id", name="uq_category_budget_user_category"),
    )

    category: Mapped["Category"] = relationship("Category")


class ActualImportMapping(Base):
    __tablename__ = "actual_import_mappings"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    actual_id: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "entity_type", "actual_id", name="uq_actual_import_mapping"),
    )


class FinancialTransaction(Base):
    __tablename__ = "financial_transactions"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())
    description: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    is_pending: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(50), nullable=False, default="human")
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")

    postings: Mapped[list["Posting"]] = relationship(
        "Posting", back_populates="transaction", cascade="all, delete-orphan"
    )


class LoanAgreement(Base):
    __tablename__ = "loan_agreements"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    payment_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint("account_id <> payment_account_id", name="ck_loan_distinct_accounts"),
        UniqueConstraint("account_id", name="uq_loan_agreement_account"),
    )


class LoanInstallment(Base):
    __tablename__ = "loan_installments"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    loan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("loan_agreements.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    number: Mapped[int] = mapped_column(nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    principal_pln: Mapped[int] = mapped_column(BigInteger, nullable=False)
    interest_pln: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fees_pln: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint("loan_id", "number", name="uq_loan_installment_number"),
        CheckConstraint("number > 0", name="ck_loan_installment_number"),
        CheckConstraint(
            "principal_pln >= 0 AND interest_pln >= 0 AND fees_pln >= 0",
            name="ck_loan_installment_components",
        ),
        CheckConstraint(
            "principal_pln + interest_pln + fees_pln > 0", name="ck_loan_installment_total"
        ),
        CheckConstraint(
            "principal_pln + interest_pln + fees_pln <= 9007199254740991",
            name="ck_loan_installment_safe_total",
        ),
    )


class LoanPaymentLink(Base):
    __tablename__ = "loan_payment_links"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    installment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("loan_installments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("financial_transactions.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )


class FinancialDocument(Base):
    __tablename__ = "financial_documents"
    __table_args__ = (
        CheckConstraint(
            "kind IS NULL OR kind IN ('invoice', 'receipt')", name="ck_financial_document_kind"
        ),
        CheckConstraint(
            "review IN ('draft', 'approved', 'rejected')", name="ck_financial_document_review"
        ),
        CheckConstraint(
            "declaration IN ('unknown', 'payable', 'declared_paid')",
            name="ck_financial_document_declaration",
        ),
        CheckConstraint(
            "lifecycle IN ('active', 'archived', 'cancelled')",
            name="ck_financial_document_lifecycle",
        ),
        CheckConstraint(
            "recurring_decision IS NULL OR recurring_decision = 'separate'",
            name="ck_financial_document_recurring_decision",
        ),
        CheckConstraint(
            "currency IS NULL OR currency IN ('PLN', 'EUR', 'USD')",
            name="ck_financial_document_currency",
        ),
        CheckConstraint(
            "total_minor IS NULL OR (total_minor > 0 AND total_minor <= 9007199254740991)",
            name="ck_financial_document_total_minor",
        ),
        CheckConstraint("version >= 1", name="ck_financial_document_version"),
        CheckConstraint(
            "review <> 'approved' OR (kind IS NOT NULL AND supplier_name IS NOT NULL "
            "AND description IS NOT NULL AND total_minor IS NOT NULL AND currency IS NOT NULL)",
            name="ck_financial_document_approved_complete",
        ),
        Index("ix_financial_documents_user_due_date", "user_id", "due_date"),
        Index("ix_financial_documents_user_review", "user_id", "review"),
        Index("ix_financial_documents_user_lifecycle", "user_id", "lifecycle"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    supplier_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    supplier_tax_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sale_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    payee_iban: Mapped[str | None] = mapped_column(String(34), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT"), nullable=True
    )
    payment_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )
    total_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    review: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default="draft"
    )
    declaration: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unknown", server_default="unknown"
    )
    lifecycle: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    recurring_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    version: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")


class FinancialDocumentSource(Base):
    __tablename__ = "financial_document_sources"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    financial_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("financial_documents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )


class DocumentPaymentAllocation(Base):
    __tablename__ = "document_payment_allocations"
    __table_args__ = (
        UniqueConstraint(
            "financial_document_id", "posting_id", name="uq_document_payment_allocation"
        ),
        CheckConstraint("amount_minor > 0", name="ck_document_payment_allocation_amount"),
        CheckConstraint(
            "amount_minor <= 9007199254740991", name="ck_document_payment_allocation_safe_amount"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    financial_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("financial_documents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    posting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("postings.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)


class RecurringOccurrenceCoverage(Base):
    __tablename__ = "recurring_occurrence_coverages"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "scheduled_item_id",
            "occurrence_date",
            name="uq_recurring_coverage_occurrence",
        ),
        UniqueConstraint("financial_document_id", name="uq_recurring_coverage_document"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    scheduled_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scheduled_finance_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    occurrence_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    financial_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("financial_documents.id", ondelete="RESTRICT"),
        nullable=False,
    )


class FinanceCommandReceipt(Base):
    __tablename__ = "finance_command_receipts"
    __table_args__ = (
        UniqueConstraint("user_id", "action", "key", name="uq_finance_command_receipt"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    result_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    version: Mapped[int | None] = mapped_column(nullable=True)
    response_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)


class Posting(Base):
    __tablename__ = "postings"

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("financial_transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    source_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="PLN")
    base_amount_pln: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fx_rate: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False, default=1.0)
    fx_rate_source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    is_budget_impact: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        CheckConstraint("direction IN ('debit', 'credit')", name="ck_posting_direction"),
    )

    transaction: Mapped["FinancialTransaction"] = relationship(
        "FinancialTransaction", back_populates="postings"
    )
    account: Mapped["Account"] = relationship("Account", back_populates="postings")
    category: Mapped["Category"] = relationship("Category", back_populates="postings")
