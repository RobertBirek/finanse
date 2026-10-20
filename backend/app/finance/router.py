import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.finance.models import FinancialTransaction, Posting
from app.finance.schemas import (
    AccountCreate,
    AccountResponse,
    AccountUpdate,
    BudgetStatusResponse,
    CashflowForecastResponse,
    CategoryBudgetCreate,
    CategoryBudgetResponse,
    CategoryBudgetUpdate,
    CategoryCreate,
    CategoryResponse,
    CategorySummaryResponse,
    CategoryUpdate,
    ExchangeCreate,
    FinanceSettingsResponse,
    FinanceSettingsUpdate,
    FinancialSummary,
    ScheduledFinanceConfirmationResponse,
    ScheduledFinanceItemCreate,
    ScheduledFinanceItemResponse,
    ScheduledFinanceItemUpdate,
    TransactionCreate,
    TransactionResponse,
    TransactionSearch,
    TransactionSearchResponse,
    TransactionUpdate,
)
from app.finance.service import (
    confirm_scheduled_item,
    create_account,
    create_budget,
    create_category,
    create_exchange_transaction,
    create_scheduled_item,
    create_transaction,
    delete_account,
    delete_budget,
    delete_category,
    delete_scheduled_item,
    delete_transaction,
    get_account,
    get_accounts,
    get_budget_status,
    get_budgets,
    get_cashflow_forecast,
    get_categories,
    get_category_summary,
    get_financial_summary,
    get_or_create_finance_settings,
    get_scheduled_items,
    get_transaction,
    get_transactions,
    search_transactions,
    update_account,
    update_budget,
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
    await db.refresh(account)
    return account


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account_endpoint(
    account_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    try:
        deleted = await delete_account(db, current_user.id, account_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    try:
        return await create_category(db, current_user.id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


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
    try:
        category = await update_category(db, current_user.id, category_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    await db.refresh(category)
    return category


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category_endpoint(
    category_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    try:
        deleted = await delete_category(db, current_user.id, category_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    type: Annotated[str | None, Query()] = None,
):
    return await get_transactions(db, current_user.id, limit=limit, offset=offset, txn_type=type)


@router.get("/transactions/search", response_model=TransactionSearchResponse)
async def search_transactions_endpoint(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    q: Annotated[str, Query(max_length=200)] = "",
    account_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    currency: Literal["PLN", "EUR", "USD"] | None = None,
    type: Literal["income", "expense", "transfer", "exchange"] | None = None,
    min_amount_pln: Annotated[int | None, Query(ge=0, le=9007199254740991)] = None,
    max_amount_pln: Annotated[int | None, Query(ge=0, le=9007199254740991)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0, le=10000000)] = 0,
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="Data od nie może być późniejsza niż data do")
    if (
        min_amount_pln is not None
        and max_amount_pln is not None
        and min_amount_pln > max_amount_pln
    ):
        raise HTTPException(status_code=422, detail="Kwota od nie może być większa niż kwota do")
    return await search_transactions(
        db,
        current_user.id,
        TransactionSearch(
            q=q,
            account_id=account_id,
            category_id=category_id,
            date_from=date_from,
            date_to=date_to,
            currency=currency,
            type=type,
            min_amount_pln=min_amount_pln,
            max_amount_pln=max_amount_pln,
            limit=limit,
            offset=offset,
        ),
    )


@router.post(
    "/transactions/exchange",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_exchange_endpoint(
    data: ExchangeCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        return await create_exchange_transaction(db, current_user.id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


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
    try:
        txn = await update_transaction(db, current_user.id, transaction_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    if txn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return txn


@router.delete("/transactions/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction_endpoint(
    transaction_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    deleted = await delete_transaction(db, current_user.id, transaction_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


@router.delete("/cashflow/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scheduled_finance_item(
    item_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    deleted = await delete_scheduled_item(db, current_user.id, item_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Scheduled item not found"
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/cashflow/items/{item_id}/confirm", response_model=ScheduledFinanceConfirmationResponse
)
async def confirm_scheduled_finance_item(
    item_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        transaction = await confirm_scheduled_item(db, current_user.id, item_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Scheduled item not found"
        )
    return ScheduledFinanceConfirmationResponse(
        transaction=TransactionResponse.model_validate(transaction)
    )


@router.get("/cashflow/forecast", response_model=CashflowForecastResponse)
async def get_cashflow_forecast_endpoint(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await get_cashflow_forecast(db, current_user.id)


@router.get("/budgets", response_model=list[CategoryBudgetResponse])
async def list_budgets(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await get_budgets(db, current_user.id)


@router.post("/budgets", response_model=CategoryBudgetResponse, status_code=status.HTTP_201_CREATED)
async def create_budget_endpoint(
    data: CategoryBudgetCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        return await create_budget(db, current_user.id, data)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Budget for this category already exists",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.patch("/budgets/{budget_id}", response_model=CategoryBudgetResponse)
async def update_budget_endpoint(
    budget_id: uuid.UUID,
    data: CategoryBudgetUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    budget = await update_budget(db, current_user.id, budget_id, data)
    if budget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    return budget


@router.delete("/budgets/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget_endpoint(
    budget_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    deleted = await delete_budget(db, current_user.id, budget_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/budget-status", response_model=BudgetStatusResponse)
async def get_budget_status_endpoint(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    month: Annotated[int | None, Query(ge=1, le=12)] = None,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
):
    return await get_budget_status(db, current_user.id, month=month, year=year)
