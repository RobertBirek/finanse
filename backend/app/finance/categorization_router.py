import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.finance.categorization import (
    apply_categorization,
    get_categorization_context,
    preview_categorization,
)
from app.finance.categorization_context import CategorizationError
from app.finance.categorization_schemas import (
    CategorizationApply,
    CategorizationContext,
    CategorizationPreview,
    CategorizationPreviewRequest,
)
from app.identity.models import User
from app.identity.router import get_current_user

router = APIRouter(prefix="/transactions/{transaction_id}/categorization")
Owner = Annotated[User, Depends(get_current_user)]
Database = Annotated[AsyncSession, Depends(get_db)]


def _error(error: Exception) -> JSONResponse:
    if isinstance(error, LookupError):
        return JSONResponse(status_code=404, content={"detail": "Transaction not found"})
    if isinstance(error, CategorizationError):
        return JSONResponse(
            status_code=error.status, content={"code": error.code, "detail": str(error)}
        )
    raise error


@router.get("", response_model=CategorizationContext)
async def get_context(
    transaction_id: uuid.UUID, current_user: Owner, db: Database
) -> CategorizationContext | JSONResponse:
    try:
        return await get_categorization_context(db, current_user.id, transaction_id)
    except LookupError as error:
        return _error(error)


@router.post("/preview", response_model=CategorizationPreview)
async def preview(
    transaction_id: uuid.UUID, data: CategorizationPreviewRequest, current_user: Owner, db: Database
) -> CategorizationPreview | JSONResponse:
    try:
        return await preview_categorization(db, current_user.id, transaction_id, data)
    except (LookupError, CategorizationError) as error:
        await db.rollback()
        return _error(error)


@router.post("/apply", response_model=CategorizationContext)
async def apply(
    transaction_id: uuid.UUID,
    data: CategorizationApply,
    current_user: Owner,
    db: Database,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
) -> CategorizationContext | JSONResponse:
    try:
        result = await apply_categorization(
            db, current_user.id, transaction_id, data, idempotency_key=idempotency_key
        )
        await db.commit()
        return result
    except (LookupError, CategorizationError) as error:
        await db.rollback()
        return _error(error)
