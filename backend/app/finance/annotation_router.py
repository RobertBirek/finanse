import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.finance.annotation_schemas import AnnotationResponse, AnnotationTag, AnnotationUpdate
from app.finance.annotations import (
    AnnotationError,
    get_annotations,
    list_annotation_tags,
    update_annotations,
)
from app.identity.models import User
from app.identity.router import get_current_user

router = APIRouter()
Owner = Annotated[User, Depends(get_current_user)]
Database = Annotated[AsyncSession, Depends(get_db)]


def _error(error: LookupError | AnnotationError) -> JSONResponse:
    if isinstance(error, LookupError):
        return JSONResponse(status_code=404, content={"detail": "Transaction not found"})
    return JSONResponse(
        status_code=error.status, content={"code": error.code, "detail": str(error)}
    )


@router.get("/transactions/{transaction_id}/annotations", response_model=AnnotationResponse)
async def get_context(
    transaction_id: uuid.UUID, current_user: Owner, db: Database
) -> AnnotationResponse | JSONResponse:
    try:
        return await get_annotations(db, current_user.id, transaction_id)
    except LookupError as error:
        return _error(error)


@router.put("/transactions/{transaction_id}/annotations", response_model=AnnotationResponse)
async def update_context(
    transaction_id: uuid.UUID,
    data: AnnotationUpdate,
    current_user: Owner,
    db: Database,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
) -> AnnotationResponse | JSONResponse:
    try:
        result = await update_annotations(
            db, current_user.id, transaction_id, data, idempotency_key=idempotency_key
        )
        await db.commit()
        return result
    except (LookupError, AnnotationError) as error:
        await db.rollback()
        return _error(error)


@router.get("/tags", response_model=list[AnnotationTag])
async def tags(
    current_user: Owner,
    db: Database,
    q: str = Query(default="", max_length=settings.FINANCE_TAG_NAME_MAX_CHARS),
    limit: int = Query(
        default=settings.FINANCE_TAG_PAGE_SIZE, ge=1, le=settings.FINANCE_TAG_PAGE_SIZE
    ),
) -> list[AnnotationTag]:
    return await list_annotation_tags(db, current_user.id, q=q, limit=limit)
