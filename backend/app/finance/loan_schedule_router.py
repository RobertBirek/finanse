"""Owner-scoped plan-only commands and immutable membership history."""

import uuid
from collections.abc import Awaitable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.finance.imports.commands import run_preparation_command
from app.finance.imports.errors import ImportError
from app.finance.loan_schedule_commands import (
    activate_schedule,
    get_schedule_revision,
    list_schedule_revisions,
)
from app.finance.loan_schedule_preview import prepare_schedule_preview
from app.finance.loan_schedule_schemas import (
    ScheduleActivateRequest,
    ScheduleCommitResult,
    SchedulePreviewDTO,
    SchedulePreviewRequest,
    ScheduleRevisionDetailDTO,
    ScheduleRevisionDTO,
)
from app.identity.models import User
from app.identity.router import get_current_user

Database = Annotated[AsyncSession, Depends(get_db)]
Owner = Annotated[User, Depends(get_current_user)]
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)]
import_routes = APIRouter()
history_routes = APIRouter()


async def _handle(operation: Awaitable[Any]) -> Any:
    try:
        return await operation
    except ImportError as error:
        return JSONResponse(
            {"code": error.code, "detail": str(error)}, status_code=error.http_status
        )
    except ValueError as error:
        return JSONResponse(
            {"code": "import_validation_failed", "detail": str(error)}, status_code=422
        )


@import_routes.post("/{batch_id}/schedule-preview", response_model=SchedulePreviewDTO)
async def preview(
    batch_id: uuid.UUID,
    data: SchedulePreviewRequest,
    current_user: Owner,
    db: Database,
    idempotency_key: Key,
) -> Any:
    return await _handle(
        run_preparation_command(
            db,
            current_user.id,
            action="bank_import.preview",
            key=idempotency_key,
            batch_id=batch_id,
            payload={"kind": "loan_schedule", **data.model_dump(mode="json")},
            operation=lambda: prepare_schedule_preview(db, current_user.id, batch_id, data),
        )
    )


@import_routes.post("/{batch_id}/activate-schedule", response_model=ScheduleCommitResult)
async def activate(
    batch_id: uuid.UUID,
    data: ScheduleActivateRequest,
    current_user: Owner,
    db: Database,
    idempotency_key: Key,
) -> Any:
    return await _handle(activate_schedule(db, current_user.id, batch_id, data, idempotency_key))


@history_routes.get("/{loan_id}/schedule-revisions", response_model=list[ScheduleRevisionDTO])
async def revisions(loan_id: uuid.UUID, current_user: Owner, db: Database) -> Any:
    return await _handle(list_schedule_revisions(db, current_user.id, loan_id))


@history_routes.get(
    "/{loan_id}/schedule-revisions/{revision_id}", response_model=ScheduleRevisionDetailDTO
)
async def revision(
    loan_id: uuid.UUID, revision_id: uuid.UUID, current_user: Owner, db: Database
) -> Any:
    async def read() -> ScheduleRevisionDetailDTO:
        result = await get_schedule_revision(db, current_user.id, loan_id, revision_id)
        if result is None:
            raise ImportError(
                "schedule_revision_not_found", "Nie znaleziono wersji harmonogramu.", 404
            )
        return result

    return await _handle(read())
