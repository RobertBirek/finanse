import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.finance import credit_cards as cards
from app.finance.credit_card_math import estimate_daily_interest
from app.finance.credit_card_schemas import (
    AllocationCreate,
    BankSchedule,
    CardConfig,
    ChargeCreate,
    InterestEstimate,
    PlanCreate,
    StatementCreate,
)
from app.identity.models import User
from app.identity.router import get_current_user

router = APIRouter(prefix="/accounts/{account_id}/credit-card")
CurrentUser = Annotated[User, Depends(get_current_user)]
Database = Annotated[AsyncSession, Depends(get_db)]


async def _call(operation: Any, *args: Any) -> Any:
    try:
        return await operation(*args)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except (cards.CardConflict, IntegrityError) as error:
        raise HTTPException(
            409, "Card record conflict; refresh and check the existing record"
        ) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.get("")
async def get_card(account_id: uuid.UUID, current_user: CurrentUser, db: Database) -> dict:
    return await _call(cards.detail, db, current_user.id, account_id)


@router.put("")
async def configure_card(
    account_id: uuid.UUID, data: CardConfig, current_user: CurrentUser, db: Database
) -> dict:
    return await _call(cards.configure, db, current_user.id, account_id, data)


@router.post("/statements", status_code=201)
async def statement(
    account_id: uuid.UUID, data: StatementCreate, current_user: CurrentUser, db: Database
) -> dict:
    return await _call(cards.create_statement, db, current_user.id, account_id, data)


@router.post("/plans", status_code=201)
async def plan(
    account_id: uuid.UUID, data: PlanCreate, current_user: CurrentUser, db: Database
) -> dict:
    return await _call(cards.create_plan, db, current_user.id, account_id, data)


@router.put("/plans/{plan_id}/schedule")
async def schedule(
    account_id: uuid.UUID,
    plan_id: uuid.UUID,
    data: BankSchedule,
    current_user: CurrentUser,
    db: Database,
) -> dict:
    return await _call(cards.replace_schedule, db, current_user.id, account_id, plan_id, data)


@router.post("/allocations", status_code=201)
async def allocation(
    account_id: uuid.UUID, data: AllocationCreate, current_user: CurrentUser, db: Database
) -> dict:
    return await _call(cards.allocate, db, current_user.id, account_id, data)


@router.delete("/allocations/{allocation_id}", status_code=204)
async def unlink(
    account_id: uuid.UUID, allocation_id: uuid.UUID, current_user: CurrentUser, db: Database
) -> Response:
    await _call(cards.remove_allocation, db, current_user.id, account_id, allocation_id)
    return Response(status_code=204)


@router.post("/charges", status_code=201)
async def charge(
    account_id: uuid.UUID, data: ChargeCreate, current_user: CurrentUser, db: Database
) -> dict:
    return await _call(cards.charge, db, current_user.id, account_id, data)


@router.get("/candidates")
async def candidates(
    account_id: uuid.UUID,
    current_user: CurrentUser,
    db: Database,
    kind: Literal["source", "payment", "charge"],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    return await _call(cards.candidates, db, current_user.id, account_id, kind, limit, offset)


@router.post("/interest-estimate")
async def interest_estimate(
    account_id: uuid.UUID, data: InterestEstimate, current_user: CurrentUser, db: Database
) -> dict:
    await _call(cards.detail, db, current_user.id, account_id)
    try:
        amount = estimate_daily_interest(data.principal_pln, data.apr, data.days)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {
        "estimated_interest_pln": amount,
        "method": "simple_ACT_365",
        "is_estimate": True,
        "grace_period_assessed": False,
    }


@router.delete("/{kind}/{record_id}", status_code=204)
async def remove_record(
    account_id: uuid.UUID,
    kind: Literal["plans", "statements", "charges"],
    record_id: uuid.UUID,
    current_user: CurrentUser,
    db: Database,
) -> Response:
    await _call(cards.remove_record, db, current_user.id, account_id, kind, record_id)
    return Response(status_code=204)
