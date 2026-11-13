"""Small person commands; authentication and CSRF inherited from finance router."""

import uuid
from collections.abc import Awaitable
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.finance.people import create_person, link_gift, unlink_gift, update_person
from app.finance.person_context import PersonError, get_person_link_context
from app.finance.person_reads import get_person, get_person_gifts, get_person_summary, list_people
from app.finance.person_schemas import (
    GiftLinkRequest,
    GiftUnlinkRequest,
    PersonCreate,
    PersonGiftPage,
    PersonLinkContext,
    PersonPage,
    PersonResponse,
    PersonSummary,
    PersonUpdate,
)
from app.identity.models import User
from app.identity.router import get_current_user

router = APIRouter()
Owner = Annotated[User, Depends(get_current_user)]
Database = Annotated[AsyncSession, Depends(get_db)]
CommandKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)]


async def _result[Model: BaseModel](
    db: AsyncSession, operation: Awaitable[Model], *, write: bool = False
) -> Model | JSONResponse:
    try:
        result = await operation
        if write:
            await db.commit()
        return result
    except (LookupError, PersonError) as error:
        if write:
            await db.rollback()
        if isinstance(error, LookupError):
            return JSONResponse(status_code=404, content={"detail": "Resource not found"})
        return JSONResponse(
            status_code=error.status, content={"code": error.code, "detail": str(error)}
        )


@router.get("/people", response_model=PersonPage)
async def people(
    current_user: Owner,
    db: Database,
    include_archived: bool = False,
    reference_account_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PersonPage:
    return await list_people(
        db,
        current_user.id,
        include_archived=include_archived,
        reference_account_id=reference_account_id,
        limit=limit,
        offset=offset,
    )


@router.post("/people", response_model=PersonResponse, status_code=201)
async def create(
    data: PersonCreate, current_user: Owner, db: Database
) -> PersonResponse | JSONResponse:
    return await _result(db, create_person(db, current_user.id, data), write=True)


@router.get("/people/{person_id}", response_model=PersonResponse)
async def details(
    person_id: uuid.UUID, current_user: Owner, db: Database
) -> PersonResponse | JSONResponse:
    return await _result(db, get_person(db, current_user.id, person_id))


@router.patch("/people/{person_id}", response_model=PersonResponse)
async def update(
    person_id: uuid.UUID, data: PersonUpdate, current_user: Owner, db: Database
) -> PersonResponse | JSONResponse:
    return await _result(db, update_person(db, current_user.id, person_id, data), write=True)


@router.get("/people/{person_id}/summary", response_model=PersonSummary)
async def summary(
    person_id: uuid.UUID, current_user: Owner, db: Database
) -> PersonSummary | JSONResponse:
    return await _result(db, get_person_summary(db, current_user.id, person_id))


@router.get("/people/{person_id}/gifts", response_model=PersonGiftPage)
async def gifts(
    person_id: uuid.UUID,
    current_user: Owner,
    db: Database,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PersonGiftPage | JSONResponse:
    return await _result(
        db, get_person_gifts(db, current_user.id, person_id, limit=limit, offset=offset)
    )


@router.get("/transactions/{transaction_id}/person-link", response_model=PersonLinkContext)
async def context(
    transaction_id: uuid.UUID, current_user: Owner, db: Database
) -> PersonLinkContext | JSONResponse:
    return await _result(db, get_person_link_context(db, current_user.id, transaction_id))


@router.put("/transactions/{transaction_id}/person-link", response_model=PersonLinkContext)
async def assign(
    transaction_id: uuid.UUID,
    data: GiftLinkRequest,
    current_user: Owner,
    db: Database,
    idempotency_key: CommandKey,
) -> PersonLinkContext | JSONResponse:
    return await _result(
        db,
        link_gift(db, current_user.id, transaction_id, data, idempotency_key=idempotency_key),
        write=True,
    )


@router.delete("/transactions/{transaction_id}/person-link", response_model=PersonLinkContext)
async def detach(
    transaction_id: uuid.UUID,
    data: GiftUnlinkRequest,
    current_user: Owner,
    db: Database,
    idempotency_key: CommandKey,
) -> PersonLinkContext | JSONResponse:
    return await _result(
        db,
        unlink_gift(db, current_user.id, transaction_id, data, idempotency_key=idempotency_key),
        write=True,
    )
