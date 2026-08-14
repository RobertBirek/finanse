import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.finance.models import FinancialTransaction, Posting
from app.finance.schemas import (
    AccountCreate,
    AccountResponse,
    AccountUpdate,
    CashflowForecastResponse,
    CategoryCreate,
    CategoryResponse,
    CategorySummaryResponse,
    CategoryUpdate,
    FinanceSettingsResponse,
    FinanceSettingsUpdate,
    FinancialSummary,
    ScheduledFinanceItemCreate,
    ScheduledFinanceItemResponse,
    ScheduledFinanceItemUpdate,
    TransactionCreate,
    TransactionResponse,
    TransactionUpdate,
)
from app.finance.service import (
    create_account,
    create_category,
    create_scheduled_item,
    create_transaction,
    get_account,
    get_accounts,
    get_cashflow_forecast,
    get_categories,
    get_category_summary,
    get_financial_summary,
    get_or_create_finance_settings,
    get_scheduled_items,
    get_transaction,
    get_transactions,
    update_account,
    update_category,
    update_finance_settings,
    update_scheduled_item,
    update_transaction,
)
from app.identity.models import User
from app.identity.router import get_current_user

router = APIRouter()


@router.post("/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account_endpoint(
    data: AccountCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        return await create_account(db, current_user.id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/accounts", response_model=list[AccountResponse])
async def list_accounts(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await get_accounts(db, current_user.id)


@router.get("/accounts/{account_id}", response_model=AccountResponse)
async def get_account_endpoint(
    account_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    account = await get_account(db, current_user.id, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


@router.patch("/accounts/{account_id}", response_model=AccountResponse)
async def update_account_endpoint(
    account_id: uuid.UUID,
    data: AccountUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    account = await update_account(db, current_user.id, account_id, data)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


@router.get("/accounts/{account_id}/transactions")
async def get_account_transactions(
    account_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    account = await get_account(db, current_user.id, account_id)
    if account is None:
        return JSONResponse(content={"detail": "Account not found"}, status_code=404)

    result = await db.execute(
        select(FinancialTransaction)
        .options(selectinload(FinancialTransaction.postings))
        .join(Posting, Posting.transaction_id == FinancialTransaction.id)
        .where(
            FinancialTransaction.user_id == current_user.id,
            Posting.account_id == account_id,
        )
        .order_by(FinancialTransaction.date.desc(), FinancialTransaction.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    txns = result.unique().scalars().all()

    return [TransactionResponse.model_validate(t) for t in txns]


@router.post("/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category_endpoint(
    data: CategoryCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await create_category(db, current_user.id, data)


@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await get_categories(db, current_user.id)


@router.patch("/categories/{category_id}", response_model=CategoryResponse)
async def update_category_endpoint(
    category_id: uuid.UUID,
    data: CategoryUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    category = await update_category(db, current_user.id, category_id, data)
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return category


@router.post(
    "/transactions", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED
)
async def create_transaction_endpoint(
    data: TransactionCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        return await create_transaction(db, current_user.id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/transactions", response_model=list[TransactionResponse])
async def list_transactions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    type: Annotated[str | None, Query()] = None,
):
    return await get_transactions(db, current_user.id, limit=limit, offset=offset, txn_type=type)


@router.get("/transactions/{transaction_id}", response_model=TransactionResponse)
async def get_transaction_endpoint(
    transaction_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    txn = await get_transaction(db, current_user.id, transaction_id)
    if txn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return txn


@router.patch("/transactions/{transaction_id}", response_model=TransactionResponse)
async def update_transaction_endpoint(
    transaction_id: uuid.UUID,
    data: TransactionUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    txn = await update_transaction(db, current_user.id, transaction_id, data)
    if txn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return txn


@router.get("/summary", response_model=FinancialSummary)
async def get_summary(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    month: Annotated[int | None, Query(ge=1, le=12)] = None,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
):
    return await get_financial_summary(db, current_user.id, month=month, year=year)


@router.get("/category-summary", response_model=CategorySummaryResponse)
async def get_category_summary_endpoint(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    month: Annotated[int | None, Query(ge=1, le=12)] = None,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
):
    return await get_category_summary(db, current_user.id, month=month, year=year)


@router.get("/cashflow/settings", response_model=FinanceSettingsResponse)
async def get_cashflow_settings(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await get_or_create_finance_settings(db, current_user.id)


@router.patch("/cashflow/settings", response_model=FinanceSettingsResponse)
async def update_cashflow_settings(
    data: FinanceSettingsUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        return await update_finance_settings(db, current_user.id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/cashflow/items", response_model=list[ScheduledFinanceItemResponse])
async def list_scheduled_finance_items(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await get_scheduled_items(db, current_user.id)


@router.post(
    "/cashflow/items",
    response_model=ScheduledFinanceItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_scheduled_finance_item(
    data: ScheduledFinanceItemCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        return await create_scheduled_item(db, current_user.id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.patch("/cashflow/items/{item_id}", response_model=ScheduledFinanceItemResponse)
async def update_scheduled_finance_item(
    item_id: uuid.UUID,
    data: ScheduledFinanceItemUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        item = await update_scheduled_item(db, current_user.id, item_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Scheduled item not found"
        )
    return item


@router.get("/cashflow/forecast", response_model=CashflowForecastResponse)
async def get_cashflow_forecast_endpoint(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await get_cashflow_forecast(db, current_user.id)
