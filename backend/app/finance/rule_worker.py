"""ARQ delivery/recovery over durable finance events; never scans transactions."""

import uuid
from datetime import UTC, datetime
from typing import Any

from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.database import async_session_factory
from app.finance.rule_event_models import TransactionRuleEvent
from app.finance.rule_events import (
    apply_rule_event,
    claim_rule_event,
    due_predicate,
    record_rule_event_failure,
)


async def dispatch_rule_events(ctx: dict[str, Any]) -> None:
    async with async_session_factory() as db:
        ids = (
            await db.scalars(
                select(TransactionRuleEvent.id)
                .where(due_predicate(datetime.now(UTC)))
                .order_by(TransactionRuleEvent.registered_at)
                .limit(settings.FINANCE_RULE_DISPATCH_BATCH)
            )
        ).all()
    for event_id in ids:
        try:
            await ctx["redis"].enqueue_job("process_rule_event", str(event_id))
        except (OSError, RuntimeError, RedisError):
            # No claim or attempt charge: periodic dispatcher will deliver again.
            continue


async def process_rule_event(ctx: dict[str, Any], event_id: str) -> str:
    try:
        parsed = uuid.UUID(event_id)
    except ValueError:
        return "invalid_id"
    async with async_session_factory() as db:
        lease = await claim_rule_event(db, parsed)
        await db.commit()
    if lease is None:
        return "not_claimed"
    try:
        async with async_session_factory() as db:
            result = await apply_rule_event(db, lease)
            await db.commit()
            return result
    except (SQLAlchemyError, ValueError, RuntimeError, OSError):
        # First session has rolled back. Persist retry separately and only for our lease.
        async with async_session_factory() as db:
            await record_rule_event_failure(db, lease, "write_failed")
            await db.commit()
        return "write_failed"
