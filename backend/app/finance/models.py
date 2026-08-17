import uuid
from datetime import date

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
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

    postings: Mapped[list["Posting"]] = relationship(
        "Posting", back_populates="account", cascade="all, delete-orphan"
    )

    @property
    def balance_pln(self) -> int:
        return getattr(self, "_balance", 0)


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
