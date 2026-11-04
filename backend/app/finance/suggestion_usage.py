"""Usage reads report only recorded tokens, never invented zero costs."""

import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.finance.categorization_context import CategorizationError
from app.finance.suggestion_client import ProviderUsage
from app.finance.suggestion_models import CategorizationLlmUsageReservation as Reservation
from app.finance.suggestion_models import CategorizationSuggestionJob as Job
from app.finance.suggestion_packet import SuggestionPacket
from app.finance.suggestion_schemas import SuggestionUsageResponse

if TYPE_CHECKING:
    from app.finance.suggestion_jobs import DispatchTicket, SuggestionLease


async def get_suggestion_usage(
    db: AsyncSession, owner: uuid.UUID, usage_date: date
) -> SuggestionUsageResponse:
    rows = (
        await db.scalars(
            select(Reservation).where(
                Reservation.user_id == owner, Reservation.usage_date == usage_date
            )
        )
    ).all()
    counts = {
        state: sum(r.state == state for r in rows)
        for state in ("reserved", "dispatching", "known", "unknown", "released")
    }
    known_input = [r.input_tokens for r in rows if r.input_tokens is not None]
    known_output = [r.output_tokens for r in rows if r.output_tokens is not None]
    limit = settings.FINANCE_SUGGESTIONS_DAILY_CALL_LIMIT
    return SuggestionUsageResponse(
        usage_date=usage_date,
        limit=limit,
        held=counts["reserved"],
        dispatched=counts["dispatching"] + counts["known"] + counts["unknown"],
        known=counts["known"],
        unknown=counts["unknown"],
        released=counts["released"],
        remaining_slots=max(0, limit - len(rows) + counts["released"]),
        known_input_tokens=sum(known_input) if known_input else None,
        known_output_tokens=sum(known_output) if known_output else None,
    )


async def quota_lock(db: AsyncSession, owner: uuid.UUID, day: date) -> None:
    await db.execute(
        select(
            func.pg_advisory_xact_lock(func.hashtext(f"suggestion-quota:{owner}:{day.isoformat()}"))
        )
    )


async def reserve_suggestion_call(
    db: AsyncSession, lease: "SuggestionLease", packet: SuggestionPacket
) -> Reservation | None:
    from app.finance.suggestion_jobs import cancel_job, live_lease, locked_job

    job = await locked_job(db, lease.job_id)
    if not job or not live_lease(job, lease) or packet.request_sha256 != job.request_sha256:
        return None
    old = await db.scalar(
        select(Reservation)
        .where(Reservation.job_id == job.id)
        .execution_options(populate_existing=True)
    )
    day = old.usage_date if old and old.state != "released" else datetime.now(UTC).date()
    await quota_lock(db, job.user_id, day)
    row = await db.scalar(
        select(Reservation)
        .where(Reservation.job_id == job.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row and row.state not in {"reserved", "released"}:
        return None
    if row is None or row.state == "released":
        used = await db.scalar(
            select(func.count())
            .select_from(Reservation)
            .where(
                Reservation.user_id == job.user_id,
                Reservation.usage_date == day,
                Reservation.state != "released",
            )
        )
        if (used or 0) >= settings.FINANCE_SUGGESTIONS_DAILY_CALL_LIMIT:
            cancel_job(job, "quota_exceeded")
            await db.flush()
            return None
    if row is None:
        row = Reservation(
            job_id=job.id,
            user_id=job.user_id,
            usage_date=day,
            reservation_version=1,
            held_by_lease_token=lease.token,
            state="reserved",
            configuration_fingerprint=job.configuration_fingerprint,
        )
        db.add(row)
    elif row.held_by_lease_token != lease.token or row.state == "released":
        row.reservation_version += 1
        row.held_by_lease_token, row.state, row.usage_date = lease.token, "reserved", day
    job.status = "reserved"
    await db.flush()
    return row


async def release_nosend_reservation(
    db: AsyncSession,
    lease: "SuggestionLease",
    reservation_id: uuid.UUID,
    expected_reservation_version: int,
    *,
    reason: str,
) -> bool:
    from app.finance.suggestion_jobs import live_lease, locked_job

    job = await locked_job(db, lease.job_id)
    if not job or not live_lease(job, lease):
        return False
    row = await db.scalar(
        select(Reservation)
        .where(
            Reservation.id == reservation_id,
            Reservation.job_id == job.id,
            Reservation.user_id == lease.owner_id,
        )
        .execution_options(populate_existing=True)
    )
    if not row:
        return False
    await quota_lock(db, lease.owner_id, row.usage_date)
    row = await db.scalar(
        select(Reservation)
        .where(Reservation.id == reservation_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        not row
        or row.state != "reserved"
        or row.reservation_version != expected_reservation_version
        or row.held_by_lease_token != lease.token
    ):
        return False
    row.state = "released"
    await db.flush()
    return True


async def release_terminal_nosend(db: AsyncSession, job: Job) -> None:
    """Internal: caller holds the job row and has made it terminal without dispatch."""
    if job.dispatch_nonce is not None:
        return
    row = await db.scalar(
        select(Reservation)
        .where(Reservation.job_id == job.id)
        .execution_options(populate_existing=True)
    )
    if row and row.state == "reserved":
        await quota_lock(db, job.user_id, row.usage_date)
        row = await db.scalar(
            select(Reservation)
            .where(Reservation.job_id == job.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row and row.state == "reserved":
            row.state = "released"


async def record_suggestion_usage(
    db: AsyncSession, ticket: "DispatchTicket", usage: ProviderUsage
) -> None:
    # Accounting deliberately does not acquire job/owner/policy locks.
    row = await db.scalar(
        select(Reservation)
        .where(
            Reservation.id == ticket.reservation_id,
            Reservation.job_id == ticket.job_id,
            Reservation.user_id == ticket.owner_id,
            Reservation.dispatch_nonce == ticket.dispatch_nonce,
            Reservation.reservation_version == ticket.reservation_version,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not row or row.state not in {"dispatching", "unknown", "known"}:
        return
    for field, value in (
        ("input_tokens", usage.input_tokens),
        ("output_tokens", usage.output_tokens),
        ("response_id_hash", usage.response_id_hash),
    ):
        old = getattr(row, field)
        if value is not None and old is not None and value != old:
            raise CategorizationError(
                "usage_conflict", "Zużycie dla tego wywołania jest już zapisane."
            )
        if field.endswith("tokens") and value is not None and (type(value) is not int or value < 0):
            raise CategorizationError("invalid_usage", "Nieprawidłowe metadane zużycia.")
        if value is not None:
            setattr(row, field, value)
    row.state = (
        "known" if row.input_tokens is not None and row.output_tokens is not None else "unknown"
    )
    await db.flush()
