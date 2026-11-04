"""ARQ transports only IDs; PostgreSQL owns all recovery and single-send admission."""

import uuid
from datetime import UTC, datetime
from typing import Any

from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.database import async_session_factory
from app.finance.suggestion_client import call_suggestion_provider
from app.finance.suggestion_config import get_suggestion_config
from app.finance.suggestion_jobs import (
    admit_suggestion_dispatch,
    claim_suggestion_job,
    finish_suggestion_job,
    prepare_suggestion_job,
    recover_suggestion_jobs,
)
from app.finance.suggestion_policy import reconcile_suggestion_policy
from app.finance.suggestion_usage import record_suggestion_usage, reserve_suggestion_call


async def process_suggestion_job(ctx: dict[str, Any], job_id: str) -> str:
    async with async_session_factory() as db:
        await reconcile_suggestion_policy(db)
        await db.commit()
    try:
        return await _process_suggestion_job(ctx, job_id)
    finally:
        # Every domain session is already closed: no global-policy/job lock inversion.
        async with async_session_factory() as db:
            await reconcile_suggestion_policy(db)
            await db.commit()


async def _process_suggestion_job(ctx: dict[str, Any], job_id: str) -> str:
    try:
        parsed = uuid.UUID(job_id)
    except ValueError:
        return "invalid_id"
    # No exception path retries a call. Uncertain commits never authorize a send.
    try:
        async with async_session_factory() as db:
            lease = await claim_suggestion_job(db, parsed)
            await db.commit()
        if lease is None:
            return "not_claimed"
        async with async_session_factory() as db:
            packet = await prepare_suggestion_job(db, lease)
            await db.commit()
        if packet is None:
            return "cancelled"
        async with async_session_factory() as db:
            reservation = await reserve_suggestion_call(db, lease, packet)
            version = reservation.reservation_version if reservation else None
            await db.commit()
        if version is None:
            return "cancelled"
        config = get_suggestion_config(settings)
        if not config:
            return "not_admitted"
        async with async_session_factory() as db:
            ticket = await admit_suggestion_dispatch(db, lease, version)
            await db.commit()
        if ticket is None:
            return "not_admitted"
    except (SQLAlchemyError, ValueError, RuntimeError, OSError):
        # Expired predispatch leases recover; any persisted dispatching is terminal uncertain.
        return "not_admitted"
    outcome = await call_suggestion_provider(packet, config)
    async with async_session_factory() as db:
        await record_suggestion_usage(db, ticket, outcome.usage)
        await db.commit()
    async with async_session_factory() as db:
        result = await finish_suggestion_job(db, ticket, outcome)
        await db.commit()
    return result


async def dispatch_suggestion_jobs(ctx: dict[str, Any]) -> None:
    async with async_session_factory() as db:
        await reconcile_suggestion_policy(db)
        await db.commit()
        ids = await recover_suggestion_jobs(db, datetime.now(UTC))
        await db.commit()
    for job_id in ids:
        try:
            await ctx["redis"].enqueue_job("process_suggestion_job", str(job_id))
        except (RedisError, OSError, RuntimeError):
            continue
