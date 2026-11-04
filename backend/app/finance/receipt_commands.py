"""Durable receipt commands: replay only an identical, owner-scoped human intent."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_event
from app.finance.categorization_context import CategorizationError, digest
from app.finance.models import FinanceCommandReceipt
from app.finance.rule_policy import policy_locks

receipt_locks = policy_locks


@dataclass
class ReceiptCommandOutcome:
    response: BaseModel
    entity_id: uuid.UUID
    version: int | None
    result_ids: list[uuid.UUID]


async def run_receipt_command(
    db: AsyncSession,
    owner: uuid.UUID,
    *,
    action: str,
    key: str,
    payload: dict[str, object],
    operation: Callable[[uuid.UUID], Awaitable[ReceiptCommandOutcome]],
) -> dict[str, object]:
    hashed = digest(payload)
    await db.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(f"receipt-command:{owner}:{action}:{key}")))
    )
    existing = await db.scalar(
        select(FinanceCommandReceipt).where(
            FinanceCommandReceipt.user_id == owner,
            FinanceCommandReceipt.action == action,
            FinanceCommandReceipt.key == key,
        )
    )
    if existing:
        if existing.request_hash != hashed:
            raise CategorizationError("idempotency_key_reused", "Klucz dotyczy innej decyzji.")
        return existing.response_json
    receipt = FinanceCommandReceipt(
        id=uuid.uuid4(),
        user_id=owner,
        action=action,
        key=key,
        request_hash=hashed,
        response_json={},
    )
    db.add(receipt)
    await db.flush([receipt])
    outcome = await operation(receipt.id)
    receipt.entity_id, receipt.version = outcome.entity_id, outcome.version
    receipt.result_ids = [str(i) for i in outcome.result_ids]
    receipt.response_json = outcome.response.model_dump(mode="json")
    await log_event(
        db,
        owner,
        "receipt_items",
        str(outcome.entity_id),
        action,
        new_state={"version": outcome.version, "result_ids": receipt.result_ids},
    )
    await db.flush()
    return receipt.response_json
