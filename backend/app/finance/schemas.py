import datetime as dt
import uuid

from pydantic import BaseModel, Field


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: str = Field(pattern=r"^(checking|savings|cash|credit|investment)$")
    currency: str = Field(default="PLN", min_length=3, max_length=3)
    is_active: bool = True


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: str | None = Field(default=None, pattern=r"^(checking|savings|cash|credit|investment)$")
    is_active: bool | None = None
    closed_at: dt.date | None = None


class AccountResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    type: str
    currency: str
    is_active: bool
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
    account_id: uuid.UUID
    category_id: uuid.UUID | None = None
    source_amount: int = Field(description="Amount in source currency minor units (grosze/centy)")
    source_currency: str = Field(default="PLN", min_length=3, max_length=3)
    base_amount_pln: int = Field(description="Equivalent amount in PLN minor units")
    fx_rate: float = Field(default=1.0, ge=0)
    fx_rate_source: str = Field(default="manual", max_length=50)
    direction: str = Field(pattern=r"^(debit|credit)$")


class PostingResponse(BaseModel):
    id: uuid.UUID
    transaction_id: uuid.UUID
    account_id: uuid.UUID
    category_id: uuid.UUID | None
    source_amount: int
    source_currency: str
    base_amount_pln: int
    fx_rate: float
    fx_rate_source: str
    direction: str
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


class FinancialSummary(BaseModel):
    accounts: list[dict]
    income_total_pln: int
    expense_total_pln: int
    net_total_pln: int
    month: int
    year: int
