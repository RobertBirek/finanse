import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.config import settings
from app.finance.categorization_context import CategorizationError
from app.finance.categorization_router import Database, Owner, _error
from app.finance.proposal_schemas import (
    ProposalApply,
    ProposalDecision,
    ProposalDetail,
    ProposalPage,
    ProposalPreview,
    ProposalVersion,
)
from app.finance.proposals import (
    apply_proposal,
    get_proposal,
    list_proposals,
    preview_proposal,
    reject_proposal,
)
from app.finance.rule_router import Key
from app.finance.suggestion_jobs import ACTIVE
from app.finance.suggestion_models import CategorizationSuggestionJob as Job
from app.finance.suggestion_policy import change_suggestion_settings, suggestion_policy_snapshot
from app.finance.suggestion_schemas import (
    SuggestionSettingsChange,
    SuggestionSettingsResponse,
    SuggestionUsageResponse,
)
from app.finance.suggestion_usage import get_suggestion_usage

router = APIRouter(prefix="/categorization")


@router.get("/suggestions/settings", response_model=SuggestionSettingsResponse)
async def suggestions_settings_get(current_user: Owner, db: Database) -> SuggestionSettingsResponse:
    return await suggestion_policy_snapshot(db, current_user.id)


@router.patch("/suggestions/settings", response_model=SuggestionSettingsResponse)
async def suggestions_settings_change(
    data: SuggestionSettingsChange, current_user: Owner, db: Database, idempotency_key: Key
):
    try:
        result = await change_suggestion_settings(
            db, current_user.id, data, idempotency_key=idempotency_key
        )
        await db.commit()
        return result
    except CategorizationError as error:
        await db.rollback()
        return _error(error)


@router.get("/suggestions/usage", response_model=SuggestionUsageResponse)
async def suggestions_usage_get(
    current_user: Owner, db: Database, date: date | None = None
) -> SuggestionUsageResponse:
    return await get_suggestion_usage(db, current_user.id, date or datetime.now(UTC).date())


@router.get("/suggestions/activity")
async def suggestions_activity_get(current_user: Owner, db: Database) -> dict[str, Any]:
    limit = settings.FINANCE_SUGGESTIONS_REVIEW_PAGE_SIZE

    def project(row: Job) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "transaction_id": str(row.transaction_id),
            "state": row.status,
            "result_kind": row.result_kind,
            "reason_code": row.reason_code,
            "updated_at": row.updated_at.isoformat(),
        }

    active = (
        await db.scalars(
            select(Job)
            .where(Job.user_id == current_user.id, Job.status.in_(ACTIVE))
            .order_by(Job.created_at, Job.id)
            .limit(limit)
        )
    ).all()
    recent = (
        await db.scalars(
            select(Job)
            .where(
                Job.user_id == current_user.id,
                Job.status.not_in(ACTIVE),
                Job.updated_at >= datetime.now(UTC) - timedelta(days=7),
            )
            .order_by(Job.updated_at.desc(), Job.id.desc())
            .limit(limit)
        )
    ).all()
    return {
        "active_jobs": [project(j) for j in active],
        "recent_outcomes": [project(j) for j in recent],
        "poll_after_ms": settings.FINANCE_SUGGESTIONS_UI_POLL_MS,
    }


@router.get("/proposals", response_model=ProposalPage)
async def proposals_get(
    current_user: Owner,
    db: Database,
    state: Literal["pending", "approved", "rejected", "stale", "expired", "superseded"] = "pending",
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
):
    try:
        return await list_proposals(db, current_user.id, state=state, cursor=cursor, limit=limit)
    except CategorizationError as error:
        return _error(error)


@router.get("/proposals/{proposal_id}", response_model=ProposalDetail)
async def proposal_get(proposal_id: uuid.UUID, current_user: Owner, db: Database):
    try:
        return await get_proposal(db, current_user.id, proposal_id)
    except LookupError as error:
        return _error(error)


@router.post("/proposals/{proposal_id}/preview", response_model=ProposalPreview)
async def proposal_preview_post(
    proposal_id: uuid.UUID, data: ProposalVersion, current_user: Owner, db: Database
):
    try:
        return await preview_proposal(db, current_user.id, proposal_id, data)
    except (LookupError, CategorizationError) as error:
        await db.rollback()
        return _error(error)


@router.post("/proposals/{proposal_id}/apply", response_model=ProposalDecision)
async def proposal_apply_post(
    proposal_id: uuid.UUID,
    data: ProposalApply,
    current_user: Owner,
    db: Database,
    idempotency_key: Key,
):
    try:
        result = await apply_proposal(
            db, current_user.id, proposal_id, data, idempotency_key=idempotency_key
        )
        await db.commit()
        return result
    except (LookupError, CategorizationError) as error:
        await db.rollback()
        return _error(error)


@router.post("/proposals/{proposal_id}/reject", response_model=ProposalDecision)
async def proposal_reject_post(
    proposal_id: uuid.UUID,
    data: ProposalVersion,
    current_user: Owner,
    db: Database,
    idempotency_key: Key,
):
    try:
        result = await reject_proposal(
            db, current_user.id, proposal_id, data, idempotency_key=idempotency_key
        )
        await db.commit()
        return result
    except (LookupError, CategorizationError) as error:
        await db.rollback()
        return _error(error)
