import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Header
from sqlalchemy import select

from app.config import settings
from app.finance.categorization_context import CategorizationError
from app.finance.categorization_router import Database, Owner, _error
from app.finance.rule_event_models import TransactionRuleEvent
from app.finance.rule_models import TransactionCategorizationRule as Rule
from app.finance.rule_policy import (
    command,
    get_rule,
    get_settings,
    policy_locks,
    rule_preview,
    rule_response,
    settings_response,
)
from app.finance.rule_schemas import RuleApproval, RuleDraft, RuleEdit, RuleVersion, SettingsChange

router = APIRouter(prefix="/categorization")
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)]


@router.get("/events")
async def rule_events_get(current_user: Owner, db: Database) -> dict[str, Any]:
    events = (
        await db.scalars(
            select(TransactionRuleEvent)
            .where(
                TransactionRuleEvent.user_id == current_user.id,
                TransactionRuleEvent.status.in_(["ready", "processing"]),
            )
            .order_by(TransactionRuleEvent.registered_at)
            .limit(settings.FINANCE_RULE_DISPATCH_BATCH)
        )
    ).all()
    return {
        "events": [
            {
                "id": str(e.id),
                "transaction_id": str(e.transaction_id),
                "status": e.status,
                "reason_code": e.reason_code,
            }
            for e in events
        ],
        "poll_after_ms": settings.FINANCE_RULE_UI_POLL_MS,
    }


async def _run(
    db: Database,
    owner: uuid.UUID,
    action: str,
    payload: Any,
    key: str,
    rule_id: uuid.UUID | None = None,
) -> Any:
    try:
        result = await command(db, owner, action, payload.model_dump(mode="json"), key, rule_id)
        await db.commit()
        return result
    except (LookupError, CategorizationError) as error:
        await db.rollback()
        return _error(error)


@router.get("/settings")
async def settings_get(current_user: Owner, db: Database) -> dict[str, Any]:
    return settings_response(await get_settings(db, current_user.id))


@router.patch("/settings")
async def settings_patch(
    data: SettingsChange, current_user: Owner, db: Database, idempotency_key: Key
) -> Any:
    return await _run(db, current_user.id, "rule_settings", data, idempotency_key)


@router.get("/rules")
async def rules_get(current_user: Owner, db: Database) -> list[dict[str, Any]]:
    return [
        rule_response(r)
        for r in (
            await db.scalars(
                select(Rule)
                .where(Rule.user_id == current_user.id)
                .order_by(Rule.created_at, Rule.id)
            )
        ).all()
    ]


@router.post("/rules", status_code=201)
async def rules_create(
    data: RuleDraft, current_user: Owner, db: Database, idempotency_key: Key
) -> Any:
    return await _run(db, current_user.id, "rule_create", data, idempotency_key)


@router.patch("/rules/{rule_id}")
async def rules_edit(
    rule_id: uuid.UUID, data: RuleEdit, current_user: Owner, db: Database, idempotency_key: Key
) -> Any:
    return await _run(db, current_user.id, "rule_edit", data, idempotency_key, rule_id)


@router.post("/rules/{rule_id}/preview")
async def rules_preview(
    rule_id: uuid.UUID, data: RuleVersion, current_user: Owner, db: Database
) -> Any:
    try:
        await policy_locks(db, current_user.id)
        rule = await get_rule(db, current_user.id, rule_id)
        if rule.version != data.expected_version or rule.state == "retired":
            raise CategorizationError("version_conflict", "Reguła zmieniła się.")
        return await rule_preview(db, current_user.id, rule)
    except (LookupError, CategorizationError) as error:
        await db.rollback()
        return _error(error)


@router.post("/rules/{rule_id}/approve")
async def rules_approve(
    rule_id: uuid.UUID, data: RuleApproval, current_user: Owner, db: Database, idempotency_key: Key
) -> Any:
    return await _run(db, current_user.id, "rule_approve", data, idempotency_key, rule_id)


@router.post("/rules/{rule_id}/pause")
async def rules_pause(
    rule_id: uuid.UUID, data: RuleVersion, current_user: Owner, db: Database, idempotency_key: Key
) -> Any:
    return await _run(db, current_user.id, "rule_pause", data, idempotency_key, rule_id)


@router.post("/rules/{rule_id}/retire")
async def rules_retire(
    rule_id: uuid.UUID, data: RuleVersion, current_user: Owner, db: Database, idempotency_key: Key
) -> Any:
    return await _run(db, current_user.id, "rule_retire", data, idempotency_key, rule_id)
