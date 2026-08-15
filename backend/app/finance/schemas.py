import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: str = Field(pattern=r"^(checking|savings|cash|credit|investment)$")
    currency: str = Field(default="PLN", min_length=3, max_length=3)
    is_active: bool = True
    is_budget_account: bool = True


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: str | None = Field(default=None, pattern=r"^(checking|savings|cash|credit|investment)$")
    is_active: bool | None = None
    is_budget_account: bool | None = None
    closed_at: dt.date | None = None


class AccountResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    type: str
    currency: str
    is_active: bool
    is_budget_account: bool
    balance_pln: int = 0
    opened_at: dt.date
    closed_at: dt.date | None
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = {"from_attributes": True}


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_id: uuid.UUID | None = None
    type: str = Field(pattern=r"^(income|expense|transfer)$")


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    parent_id: uuid.UUID | None = None
    type: str | None = Field(default=None, pattern=r"^(income|expense|transfer)$")


class CategoryResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    type: str
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = {"from_attributes": True}


class PostingCreate(BaseModel):
    account_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    source_amount: int = Field(description="Amount in source currency minor units (grosze/centy)")
    source_currency: str = Field(default="PLN", min_length=3, max_length=3)
    base_amount_pln: int = Field(description="Equivalent amount in PLN minor units")
    fx_rate: float = Field(default=1.0, ge=0)
    fx_rate_source: str = Field(default="manual", max_length=50)
    direction: str = Field(pattern=r"^(debit|credit)$")
    is_budget_impact: bool = True


class PostingResponse(BaseModel):
    id: uuid.UUID
    transaction_id: uuid.UUID
    account_id: uuid.UUID | None
    category_id: uuid.UUID | None
    source_amount: int
    source_currency: str
    base_amount_pln: int
    fx_rate: float
    fx_rate_source: str
    direction: str
    is_budget_impact: bool
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = {"from_attributes": True}


class TransactionCreate(BaseModel):
    transaction_date: dt.date | None = None
    description: str = Field(min_length=1)
    type: str = Field(pattern=r"^(income|expense|transfer|exchange)$")
    is_pending: bool = False
    project_id: uuid.UUID | None = None
    source: str = Field(default="manual", max_length=50)
    postings: list[PostingCreate] = Field(min_length=2)


class TransactionUpdate(BaseModel):
    transaction_date: dt.date | None = None
    description: str | None = None
    is_pending: bool | None = None
    project_id: uuid.UUID | None = None


class TransactionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    transaction_date: dt.date = Field(validation_alias="date")
    description: str
    type: str
    is_pending: bool
    project_id: uuid.UUID | None
    created_by: str
    source: str
    postings: list[PostingResponse]
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = {"from_attributes": True}


class ScheduledFinanceConfirmationResponse(BaseModel):
    transaction: TransactionResponse


class FinancialSummary(BaseModel):
    accounts: list[dict]
    income_total_pln: int
    expense_total_pln: int
    net_total_pln: int
    month: int
    year: int


class CategorySpendResponse(BaseModel):
    category_id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    total_pln: int


class CategorySummaryResponse(BaseModel):
    month: int
    year: int
    groups: list[CategorySpendResponse]
    categories: list[CategorySpendResponse]


class FinanceSettingsUpdate(BaseModel):
    payday_day: int | None = Field(default=None, ge=1, le=28)
    payday_account_id: uuid.UUID | None = None
    forecast_horizon_days: int | None = Field(default=None, ge=1, le=90)
    overdue_grace_days: int | None = Field(default=None, ge=0, le=14)


class FinanceSettingsResponse(BaseModel):
    payday_day: int
    payday_account_id: uuid.UUID | None
    forecast_horizon_days: int
    overdue_grace_days: int

    model_config = {"from_attributes": True}


class ScheduledFinanceItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: Literal["income", "expense"]
    account_id: uuid.UUID
    category_id: uuid.UUID
    currency: str = Field(min_length=3, max_length=3)
    due_day: int = Field(ge=1, le=28)
    amount_method: Literal["fixed", "last_actual"]
    fixed_amount_pln: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_amount_method(self) -> "ScheduledFinanceItemCreate":
        if self.amount_method == "fixed" and self.fixed_amount_pln is None:
            raise ValueError("fixed_amount_pln is required for fixed amount_method")
        if self.amount_method == "last_actual" and self.fixed_amount_pln is not None:
            raise ValueError("fixed_amount_pln must be omitted for last_actual amount_method")
        self.currency = self.currency.upper()
        return self


class ScheduledFinanceItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    account_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    due_day: int | None = Field(default=None, ge=1, le=28)
    amount_method: Literal["fixed", "last_actual"] | None = None
    fixed_amount_pln: int | None = Field(default=None, gt=0)
    is_active: bool | None = None


class ScheduledFinanceItemResponse(BaseModel):
    id: uuid.UUID
    name: str
    type: Literal["income", "expense"]
    account_id: uuid.UUID
    category_id: uuid.UUID
    currency: str
    cadence: Literal["monthly"]
    due_day: int
    amount_method: Literal["fixed", "last_actual"]
    fixed_amount_pln: int | None
    is_active: bool

    model_config = {"from_attributes": True}


class CashflowDay(BaseModel):
    date: dt.date
    projected_balance_pln: int


class CashflowSuggestion(BaseModel):
    scheduled_item_id: uuid.UUID
    name: str
    type: Literal["income", "expense"]
    due_date: dt.date
    amount_pln: int | None
    status: Literal["due", "overdue", "overdue_uncertain", "matched_actual", "amount_unknown"]
    included_in_forecast: bool
    actual_transaction_id: uuid.UUID | None = None


class CashflowForecastResponse(BaseModel):
    last_payday: dt.date
    next_payday: dt.date
    opening_balance_pln: int
    projected_balance_before_next_payday_pln: int
    safe_daily_limit_pln: int
    lowest_balance_pln: int
    days: list[CashflowDay]
    suggestions: list[CashflowSuggestion]


class CategoryBudgetCreate(BaseModel):
    category_id: uuid.UUID
    amount_pln: int = Field(gt=0)


class CategoryBudgetUpdate(BaseModel):
    amount_pln: int = Field(gt=0)


class CategoryBudgetResponse(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID
    amount_pln: int

    model_config = {"from_attributes": True}


class BudgetStatusItem(BaseModel):
    category_id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    budget_amount_pln: int
    spent_pln: int
    remaining_pln: int


class BudgetStatusResponse(BaseModel):
    month: int
    year: int
    items: list[BudgetStatusItem]
