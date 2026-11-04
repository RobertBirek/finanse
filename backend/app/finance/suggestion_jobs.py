"""Durable, creation-only generation with separate dispatch and publication authority."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.finance.categorization_context import CategorizationError, LedgerContext, load_context
from app.finance.categorization_enrollment import CreationObservation, observe_creation_policy
from app.finance.models import FinancialTransaction
from app.finance.rule_events import eligible_unclassified
from app.finance.rule_policy import get_settings, policy_locks
from app.finance.suggestion_client import ProviderOutcome
from app.finance.suggestion_config import SuggestionConfig, get_suggestion_config
from app.finance.suggestion_models import (
    CategorizationLlmUsageReservation as Reservation,
)
from app.finance.suggestion_models import (
    CategorizationProposalItem as Item,
)
from app.finance.suggestion_models import (
    CategorizationSuggestionJob as Job,
)
from app.finance.suggestion_packet import SuggestionPacket, build_suggestion_packet
from app.finance.suggestion_policy import current_consent, current_policy
from app.identity.models import User

PREDISPATCH = ("ready", "preparing", "reserved")
ACTIVE = (*PREDISPATCH, "dispatching")


@dataclass(frozen=True)
class SuggestionLease:
    job_id: uuid.UUID
    owner_id: uuid.UUID
    token: uuid.UUID


@dataclass(frozen=True)
class DispatchTicket:
    job_id: uuid.UUID
    owner_id: uuid.UUID
    lease_token: uuid.UUID
    dispatch_nonce: uuid.UUID
    reservation_id: uuid.UUID
    reservation_version: int


async def record_new_suggestion_intent(
    db: AsyncSession, owner: uuid.UUID, txn: FinancialTransaction, observation: CreationObservation
) -> uuid.UUID | None:
    o = observation
    if not o.configuration_ready or not o.marker_id or (o.rules_enabled and o.rule_candidates):
        return None
    ctx = await load_context(db, owner, txn.id)
    if not eligible_unclassified(ctx, o.marker_id):
        return None
    await db.execute(
        insert(Job)
        .values(
            user_id=owner,
            transaction_id=txn.id,
            source_context_sha256=ctx.snapshot(),
            marker_id=o.marker_id,
            settings_version=o.settings_version,
            user_epoch=o.user_epoch,
            server_epoch=o.server_epoch,
            configuration_fingerprint=o.fingerprint,
            status="ready",
            attempts=0,
        )
        .on_conflict_do_nothing(constraint="uq_suggestion_creation")
    )
    return await db.scalar(select(Job.id).where(Job.user_id == owner, Job.transaction_id == txn.id))


async def locked_job(
    db: AsyncSession, job_id: uuid.UUID, *, skip_locked: bool = False
) -> Job | None:
    return await db.scalar(
        select(Job)
        .where(Job.id == job_id)
        .with_for_update(skip_locked=skip_locked)
        .execution_options(populate_existing=True)
    )


def live_lease(
    job: Job | None, lease: SuggestionLease, *, statuses: tuple[str, ...] = PREDISPATCH
) -> bool:
    return bool(
        job
        and job.user_id == lease.owner_id
        and job.status in statuses
        and job.lease_token == lease.token
        and job.lease_deadline
        and job.lease_deadline > datetime.now(UTC)
    )


def cancel_job(job: Job, reason: str) -> None:
    job.status, job.reason_code, job.next_attempt_at = "cancelled", reason, None
    job.lease_token = job.lease_deadline = None


async def claim_suggestion_job(db: AsyncSession, job_id: uuid.UUID) -> SuggestionLease | None:
    job = await locked_job(db, job_id, skip_locked=True)
    now = datetime.now(UTC)
    if not job or job.status not in PREDISPATCH:
        return None
    if (job.next_attempt_at and job.next_attempt_at > now) or (
        job.lease_deadline and job.lease_deadline > now
    ):
        return None
    if (
        job.created_at < now - timedelta(hours=settings.FINANCE_SUGGESTIONS_MAX_JOB_AGE_HOURS)
        or job.attempts >= settings.FINANCE_SUGGESTIONS_MAX_ATTEMPTS
    ):
        cancel_job(
            job,
            "job_expired"
            if job.attempts < settings.FINANCE_SUGGESTIONS_MAX_ATTEMPTS
            else "attempts_exhausted",
        )
        from app.finance.suggestion_usage import release_terminal_nosend

        await release_terminal_nosend(db, job)
        await db.flush()
        return None
    job.status = "preparing"
    job.attempts += 1
    job.lease_token = uuid.uuid4()
    job.lease_deadline = now + timedelta(seconds=settings.FINANCE_SUGGESTIONS_LEASE_SECONDS)
    await db.flush()
    return SuggestionLease(job.id, job.user_id, job.lease_token)


async def validated_context(db: AsyncSession, job: Job) -> tuple[LedgerContext, SuggestionConfig]:
    ctx = await load_context(db, job.user_id, job.transaction_id, lock=True)
    active = await db.scalar(
        select(User.is_active).where(User.id == job.user_id).with_for_update(read=True)
    )
    if active is not True:
        raise CategorizationError("owner_inactive", "Właściciel nie jest aktywny.")
    rules = await get_settings(db, job.user_id)
    consent = await current_consent(db, job.user_id, lock=True)
    server = await current_policy(db, lock=True)
    config = get_suggestion_config(settings)
    if (
        not config
        or not consent
        or not consent.enabled
        or consent.version != job.user_epoch
        or not server
        or not server.enabled
        or server.epoch != job.server_epoch
        or server.configuration_fingerprint != config.fingerprint
        or consent.accepted_server_epoch != server.epoch
        or consent.accepted_configuration_fingerprint != config.fingerprint
        or job.configuration_fingerprint != config.fingerprint
    ):
        raise CategorizationError("consent_changed", "Zgoda na generowanie zmieniła się.")
    if (
        not rules
        or rules.version != job.settings_version
        or rules.uncategorized_category_id != job.marker_id
        or not eligible_unclassified(ctx, job.marker_id)
        or ctx.snapshot() != job.source_context_sha256
    ):
        raise CategorizationError("source_changed", "Źródło lub kategoria techniczna zmieniły się.")
    observation = await observe_creation_policy(db, job.user_id, ctx.txn.description)
    if observation.rules_enabled and observation.rule_candidates:
        raise CategorizationError("rule_priority", "Zatwierdzona reguła ma pierwszeństwo.")
    if job.created_at < datetime.now(UTC) - timedelta(hours=config.max_job_age_hours):
        raise CategorizationError("job_expired", "Zadanie jest za stare.")
    return ctx, config


async def prepare_suggestion_job(
    db: AsyncSession, lease: SuggestionLease
) -> SuggestionPacket | None:
    await policy_locks(db, lease.owner_id)
    job = await locked_job(db, lease.job_id)
    if not live_lease(job, lease):
        return None
    assert job is not None
    try:
        ctx, config = await validated_context(db, job)
        packet = build_suggestion_packet(ctx, config, marker_id=job.marker_id)
        if job.request_sha256 and job.request_sha256 != packet.request_sha256:
            raise CategorizationError("taxonomy_changed", "Katalog kategorii zmienił się.")
    except (LookupError, CategorizationError) as error:
        cancel_job(job, error.code if isinstance(error, CategorizationError) else "source_missing")
        from app.finance.suggestion_usage import release_terminal_nosend

        await release_terminal_nosend(db, job)
        await db.flush()
        return None
    job.packet_json = packet.public_request
    job.private_key_map = {k: str(v) for k, v in packet.private_key_map.items()}
    job.taxonomy_sha256, job.request_sha256 = packet.taxonomy_sha256, packet.request_sha256
    await db.flush()
    return packet


async def admit_suggestion_dispatch(
    db: AsyncSession, lease: SuggestionLease, reservation_version: int
) -> DispatchTicket | None:
    await policy_locks(db, lease.owner_id)
    job = await locked_job(db, lease.job_id)
    if not live_lease(job, lease) or not job or job.status != "reserved":
        return None
    try:
        ctx, config = await validated_context(db, job)
        packet = build_suggestion_packet(ctx, config, marker_id=job.marker_id)
        if (
            packet.request_sha256 != job.request_sha256
            or packet.taxonomy_sha256 != job.taxonomy_sha256
        ):
            raise CategorizationError("taxonomy_changed", "Katalog kategorii zmienił się.")
    except (LookupError, CategorizationError) as error:
        cancel_job(job, error.code if isinstance(error, CategorizationError) else "source_missing")
        from app.finance.suggestion_usage import release_terminal_nosend

        await release_terminal_nosend(db, job)
        return None
    day = await db.scalar(select(Reservation.usage_date).where(Reservation.job_id == job.id))
    if day is None:
        return None
    from app.finance.suggestion_usage import quota_lock

    await quota_lock(db, job.user_id, day)
    reservation = await db.scalar(
        select(Reservation)
        .where(Reservation.job_id == job.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        not reservation
        or reservation.state != "reserved"
        or reservation.reservation_version != reservation_version
        or reservation.held_by_lease_token != lease.token
        or reservation.user_id != lease.owner_id
    ):
        return None
    # A wait for source/policy locks may have consumed our lease after its first check.
    if not live_lease(job, lease):
        return None
    nonce = uuid.uuid4()
    job.status, job.dispatch_nonce = "dispatching", nonce
    reservation.state, reservation.dispatch_nonce = "dispatching", nonce
    await db.flush()
    return DispatchTicket(
        job.id, job.user_id, lease.token, nonce, reservation.id, reservation.reservation_version
    )


async def finish_suggestion_job(
    db: AsyncSession, ticket: DispatchTicket, outcome: ProviderOutcome
) -> str:
    # Caller has durably recorded usage in a separate transaction before publication.
    await policy_locks(db, ticket.owner_id)
    job = await locked_job(db, ticket.job_id)
    lease = SuggestionLease(ticket.job_id, ticket.owner_id, ticket.lease_token)
    if (
        not live_lease(job, lease, statuses=("dispatching",))
        or not job
        or job.dispatch_nonce != ticket.dispatch_nonce
    ):
        return "lease_lost"
    try:
        ctx, config = await validated_context(db, job)
        packet = build_suggestion_packet(ctx, config, marker_id=job.marker_id)
        if (
            packet.taxonomy_sha256 != job.taxonomy_sha256
            or packet.request_sha256 != job.request_sha256
        ):
            raise CategorizationError("taxonomy_changed", "Katalog kategorii zmienił się.")
    except (LookupError, CategorizationError) as error:
        cancel_job(job, error.code if isinstance(error, CategorizationError) else "source_missing")
        await db.flush()
        return "cancelled"
    if not live_lease(job, lease, statuses=("dispatching",)):
        return "lease_lost"
    if outcome.error_code or outcome.payload is None:
        job.status = "uncertain" if outcome.uncertain else "failed"
        job.reason_code = outcome.error_code or "invalid_output"
    else:
        p = outcome.payload
        target = packet.private_key_map.get(p.category_key) if p.category_key else None
        if p.decision == "existing_category" and target is None:
            job.status, job.reason_code = "failed", "invalid_output"
        else:
            job.status, job.result_kind = "completed", p.decision
            if p.decision != "no_suggestion":
                db.add(
                    Item(
                        user_id=job.user_id,
                        job_id=job.id,
                        transaction_id=ctx.txn.id,
                        source_context_sha256=job.source_context_sha256,
                        request_sha256=packet.request_sha256,
                        taxonomy_sha256=packet.taxonomy_sha256,
                        generated_description=ctx.txn.description,
                        private_key_map=job.private_key_map,
                        decision=p.decision,
                        target_category_id=target,
                        new_category=p.new_category.model_dump() if p.new_category else None,
                        explanation=p.explanation,
                        confidence=p.confidence,
                        version=1,
                        status="pending",
                        expires_at=datetime.now(UTC) + timedelta(days=config.ttl_days),
                    )
                )
    job.lease_token = job.lease_deadline = None
    await db.flush()
    return job.status


async def recover_suggestion_jobs(db: AsyncSession, now: datetime) -> list[uuid.UUID]:
    jobs = (
        await db.scalars(
            select(Job)
            .where(
                Job.status.in_(ACTIVE),
                or_(
                    Job.lease_deadline <= now,
                    and_(
                        Job.status == "ready",
                        or_(Job.next_attempt_at.is_(None), Job.next_attempt_at <= now),
                    ),
                ),
            )
            .order_by(Job.created_at, Job.id)
            .limit(settings.FINANCE_SUGGESTIONS_DISPATCH_BATCH)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
    ).all()
    ready = []
    for job in jobs:
        if job.status == "dispatching":
            job.status, job.reason_code = "uncertain", "dispatch_lease_expired"
            job.lease_token = job.lease_deadline = None
            row = await db.scalar(
                select(Reservation)
                .where(Reservation.job_id == job.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if row and row.state == "dispatching":
                row.state = "unknown"
        elif (
            job.created_at < now - timedelta(hours=settings.FINANCE_SUGGESTIONS_MAX_JOB_AGE_HOURS)
            or job.attempts >= settings.FINANCE_SUGGESTIONS_MAX_ATTEMPTS
        ):
            cancel_job(
                job,
                "job_expired"
                if job.attempts < settings.FINANCE_SUGGESTIONS_MAX_ATTEMPTS
                else "attempts_exhausted",
            )
            from app.finance.suggestion_usage import release_terminal_nosend

            await release_terminal_nosend(db, job)
        else:
            # A lease recovery is demonstrably before dispatch; still bounded by attempts/age.
            if job.status != "ready":
                job.status, job.lease_token, job.lease_deadline = "ready", None, None
                delay = (
                    settings.FINANCE_SUGGESTIONS_RETRY_INITIAL_SECONDS
                    if job.attempts <= 1
                    else settings.FINANCE_SUGGESTIONS_RETRY_LATER_SECONDS
                )
                job.next_attempt_at = now + timedelta(seconds=delay)
            else:
                ready.append(job.id)
    await db.flush()
    return ready
