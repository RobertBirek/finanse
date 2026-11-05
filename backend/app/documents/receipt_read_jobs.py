"""Durable content streams. A fresh client key alone never authorizes another export."""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_event
from app.config import settings
from app.documents.receipt_read_client import ReceiptReadProviderOutcome
from app.documents.receipt_read_config import ReceiptReadConfig
from app.documents.receipt_read_models import (
    ReceiptReadExtraction,
    ReceiptReadJob,
    ReceiptReadReservation,
    ReceiptReadStream,
    ReceiptReadUsage,
)
from app.documents.receipt_read_payload import (
    build_receipt_read_proposal,
    validate_receipt_read_intake,
)
from app.documents.receipt_read_policy import (
    receipt_read_admission,
    receipt_read_allowed,
    reconcile_receipt_read_policy,
)
from app.documents.receipt_read_schemas import (
    READ_ACTIVE_STATES,
    ReceiptReadJobState,
    ReceiptReadJobView,
    ReceiptReadStart,
)
from app.finance.categorization_context import CategorizationError, digest
from app.finance.receipt_read_context import load_receipt_read_source, owned_receipt_read_document

if TYPE_CHECKING:
    from app.finance.receipt_read_context import ReceiptReadSource


def receipt_read_job_view(
    job: ReceiptReadJob, extraction_id: uuid.UUID | None = None
) -> ReceiptReadJobView:
    active = job.state in READ_ACTIVE_STATES
    return ReceiptReadJobView(
        id=job.id,
        bill_id=job.bill_id,
        document_id=job.document_id,
        generation=job.generation,
        version=job.version,
        state=cast(ReceiptReadJobState, job.state),
        source_sha256=job.source_sha256,
        dispatched=job.dispatch_token is not None,
        extraction_id=extraction_id,
        error_code=job.error_code,
        can_cancel=job.state in {"pending", "preparing"} and job.dispatch_token is None,
        poll_after_ms=settings.DOCUMENT_RECEIPT_ITEMS_POLL_MS if active else None,
        created_at=job.created_at,
    )


async def lock_receipt_read_stream(
    db: AsyncSession,
    owner: uuid.UUID,
    bill_id: uuid.UUID,
    source_sha256: str,
    configuration_fingerprint: str,
    *,
    lock: bool,
) -> tuple[ReceiptReadStream | None, ReceiptReadJob | None]:
    q = (
        select(ReceiptReadStream)
        .where(
            ReceiptReadStream.user_id == owner,
            ReceiptReadStream.bill_id == bill_id,
            ReceiptReadStream.source_sha256 == source_sha256,
            ReceiptReadStream.configuration_fingerprint == configuration_fingerprint,
        )
        .execution_options(populate_existing=True)
    )
    stream = await db.scalar(q.with_for_update() if lock else q)
    job = None
    if stream and stream.latest_job_id:
        j = (
            select(ReceiptReadJob)
            .where(
                ReceiptReadJob.id == stream.latest_job_id,
                ReceiptReadJob.user_id == owner,
                ReceiptReadJob.stream_id == stream.id,
            )
            .execution_options(populate_existing=True)
        )
        job = await db.scalar(j.with_for_update() if lock else j)
    return stream, job


async def admit_receipt_read(
    db: AsyncSession,
    owner: uuid.UUID,
    source: "ReceiptReadSource",
    data: ReceiptReadStart,
    *,
    grant_receipt_id: uuid.UUID,
    config: ReceiptReadConfig,
    now: datetime,
) -> ReceiptReadJob:
    # Caller has already locked existing stream/job BEFORE Finance gates. New FK-bearing
    # rows are only inserted AFTER those gates to avoid a hidden bill KEY SHARE edge.
    stream, prior = await lock_receipt_read_stream(
        db,
        owner,
        source.bill.id,
        source.document.sha256_hash,
        config.configuration_fingerprint,
        lock=True,
    )
    if prior and data.reread_of_job_id is None:
        return prior
    if data.reread_of_job_id and (
        not prior or prior.id != data.reread_of_job_id or prior.state in READ_ACTIVE_STATES
    ):
        raise CategorizationError(
            "read_generation_changed", "Wybierz aktualną zakończoną próbę i potwierdź nowy koszt."
        )
    for own, cap in [
        (False, settings.DOCUMENT_RECEIPT_ITEMS_QUEUE_LIMIT_GLOBAL),
        (True, settings.DOCUMENT_RECEIPT_ITEMS_QUEUE_LIMIT_PER_USER),
    ]:
        q = (
            select(func.count())
            .select_from(ReceiptReadJob)
            .where(ReceiptReadJob.state.in_(READ_ACTIVE_STATES))
        )
        if own:
            q = q.where(ReceiptReadJob.user_id == owner)
        if (await db.scalar(q) or 0) >= cap:
            raise CategorizationError(
                "receipt_read_queue_full", "Kolejka odczytu jest pełna. Spróbuj później."
            )
    if stream is None:
        stream = ReceiptReadStream(
            user_id=owner,
            bill_id=source.bill.id,
            source_sha256=source.document.sha256_hash,
            configuration_fingerprint=config.configuration_fingerprint,
            version=1,
        )
        db.add(stream)
        await db.flush([stream])
    else:
        stream.version += 1
    from app.documents.receipt_read_policy import get_receipt_read_policy

    policy = await get_receipt_read_policy(db)
    job = ReceiptReadJob(
        id=uuid.uuid4(),
        user_id=owner,
        stream_id=stream.id,
        bill_id=source.bill.id,
        document_id=source.document.id,
        generation=1 if prior is None else prior.generation + 1,
        source_sha256=source.document.sha256_hash,
        header_sha256=source.header_sha256,
        configuration_fingerprint=config.configuration_fingerprint,
        policy_epoch=policy.epoch,
        consent_json={
            "document_id": str(source.document.id),
            "bill_id": str(source.bill.id),
            "source_sha256": source.document.sha256_hash,
            "header_sha256": source.header_sha256,
            "purpose": "receipt_items",
            "configuration_fingerprint": config.configuration_fingerprint,
            "consent_version": config.consent_version,
            "export_snapshot": data.expected_export_snapshot,
            "confirmed_at": now.astimezone(UTC).isoformat(),
        },
        grant_receipt_id=grant_receipt_id,
        state="pending",
        version=1,
    )
    db.add(job)
    await db.flush([job])
    stream.latest_job_id = job.id
    await db.flush()
    return job


@dataclass(frozen=True)
class ReceiptReadClaim:
    job_id: uuid.UUID
    user_id: uuid.UUID
    bill_id: uuid.UUID
    document_id: uuid.UUID
    stream_id: uuid.UUID
    lease_token: uuid.UUID
    source_sha256: str
    header_sha256: str
    policy_epoch: int
    configuration_fingerprint: str


@dataclass(frozen=True)
class ReceiptReadPrepared:
    jpeg: bytes
    derivative_sha256: str
    pixel_upper_bound: int


def _terminal(job: ReceiptReadJob, state: str, code: str | None = None) -> None:
    job.state = state
    job.error_code = code
    job.version += 1
    job.lease_token = None
    job.lease_expires_at = None
    job.next_attempt_at = None


async def _locked_read(
    db: AsyncSession, job_id: uuid.UUID, config: ReceiptReadConfig
) -> tuple[ReceiptReadJob | None, "ReceiptReadSource | None"]:
    await receipt_read_admission(db)
    policy = await reconcile_receipt_read_policy(db, config)
    locator = await db.scalar(
        select(ReceiptReadJob)
        .where(ReceiptReadJob.id == job_id)
        .execution_options(populate_existing=True)
    )
    if not locator:
        return None, None
    try:
        document = await owned_receipt_read_document(
            db, locator.user_id, locator.document_id, lock=True
        )
    except LookupError:
        return None, None
    await db.scalar(
        select(ReceiptReadStream)
        .where(ReceiptReadStream.id == locator.stream_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    job = await db.scalar(
        select(ReceiptReadJob)
        .where(ReceiptReadJob.id == job_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert job is not None
    if job.state not in READ_ACTIVE_STATES:
        return job, None
    if (
        not receipt_read_allowed(policy, config)
        or job.policy_epoch != policy.epoch
        or job.configuration_fingerprint != config.configuration_fingerprint
    ):
        _terminal(
            job, "superseded" if job.dispatch_token else "paused", "receipt_read_policy_changed"
        )
        return job, None
    try:
        source = await load_receipt_read_source(db, job.user_id, job.bill_id, document, lock=True)
    except (CategorizationError, LookupError):
        _terminal(
            job, "superseded" if job.dispatch_token else "paused", "receipt_read_source_changed"
        )
        return job, None
    stream = await db.get(ReceiptReadStream, job.stream_id)
    if (
        document.sha256_hash != job.source_sha256
        or source.header_sha256 != job.header_sha256
        or not stream
        or stream.latest_job_id != job.id
    ):
        _terminal(
            job, "superseded" if job.dispatch_token else "paused", "receipt_read_context_changed"
        )
        return job, None
    return job, source


def _claim_matches(job: ReceiptReadJob, claim: ReceiptReadClaim, now: datetime) -> bool:
    return bool(
        job.lease_token == claim.lease_token
        and job.lease_expires_at
        and job.lease_expires_at > now
        and job.policy_epoch == claim.policy_epoch
        and job.configuration_fingerprint == claim.configuration_fingerprint
        and job.source_sha256 == claim.source_sha256
        and job.header_sha256 == claim.header_sha256
    )


async def claim_receipt_read(
    db: AsyncSession, job_id: uuid.UUID, *, now: datetime, config: ReceiptReadConfig
) -> ReceiptReadClaim | None:
    job, source = await _locked_read(db, job_id, config)
    if job is None or source is None or job.dispatch_token:
        return None
    if job.state == "preparing" and job.lease_expires_at and job.lease_expires_at > now:
        return None
    if job.state not in {"pending", "preparing"} or (
        job.next_attempt_at and job.next_attempt_at > now
    ):
        return None
    if job.prepare_attempts >= settings.DOCUMENT_RECEIPT_ITEMS_PREPARE_MAX_ATTEMPTS:
        _terminal(job, "failed", "preparation_exhausted")
        return None
    active = (
        await db.scalar(
            select(func.count())
            .select_from(ReceiptReadJob)
            .where(
                ReceiptReadJob.state.in_({"preparing", "dispatched"}), ReceiptReadJob.id != job.id
            )
        )
        or 0
    )
    if active >= settings.DOCUMENT_RECEIPT_ITEMS_CONCURRENCY:
        return None
    job.state = "preparing"
    job.prepare_attempts += 1
    job.version += 1
    job.lease_token = uuid.uuid4()
    job.lease_expires_at = now + timedelta(seconds=settings.DOCUMENT_RECEIPT_ITEMS_LEASE_SECONDS)
    job.next_attempt_at = None
    await db.flush()
    return ReceiptReadClaim(
        job.id,
        job.user_id,
        job.bill_id,
        job.document_id,
        job.stream_id,
        job.lease_token,
        job.source_sha256,
        job.header_sha256,
        job.policy_epoch,
        job.configuration_fingerprint,
    )


async def reserve_receipt_read_dispatch(
    db: AsyncSession,
    claim: ReceiptReadClaim,
    prepared: ReceiptReadPrepared,
    *,
    now: datetime,
    config: ReceiptReadConfig,
) -> bool:
    job, source = await _locked_read(db, claim.job_id, config)
    if (
        job is None
        or source is None
        or job.state != "preparing"
        or job.dispatch_token
        or not _claim_matches(job, claim, now)
    ):
        return False
    if (
        not prepared.jpeg
        or len(prepared.jpeg) > config.max_bytes
        or not 0 < prepared.pixel_upper_bound <= config.max_pixels
        or prepared.derivative_sha256 != hashlib.sha256(prepared.jpeg).hexdigest()
    ):
        _terminal(job, "failed", "image_limit")
        return False
    active = (
        await db.scalar(
            select(func.count())
            .select_from(ReceiptReadJob)
            .where(ReceiptReadJob.state.in_({"preparing", "dispatched"}))
        )
        or 0
    )
    if active > settings.DOCUMENT_RECEIPT_ITEMS_CONCURRENCY:
        _terminal(job, "failed", "concurrency_limit")
        return False
    day = now.astimezone(UTC).date()
    scopes = [
        ("global", settings.DOCUMENT_RECEIPT_ITEMS_DAILY_CALL_LIMIT_GLOBAL),
        (f"user:{claim.user_id}", settings.DOCUMENT_RECEIPT_ITEMS_DAILY_CALL_LIMIT_PER_USER),
    ]
    rows = []
    for scope, cap in scopes:
        # Admission serializes both users and the UTC day rollover. Unique scope/day
        # is still the DB backstop; no insert at preview or claim.
        await db.execute(
            insert(ReceiptReadUsage)
            .values(id=uuid.uuid4(), scope_key=scope, usage_date=day, reserved_calls=0)
            .on_conflict_do_nothing(constraint="uq_read_usage_scope_date")
        )
        usage = await db.scalar(
            select(ReceiptReadUsage)
            .where(ReceiptReadUsage.scope_key == scope, ReceiptReadUsage.usage_date == day)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        assert usage is not None
        if usage.reserved_calls >= cap:
            _terminal(job, "failed", "daily_call_limit")
            return False
        rows.append(usage)
    for usage in rows:
        usage.reserved_calls += 1
    job.dispatch_token = claim.lease_token
    job.dispatched_at = now
    job.state = "dispatched"
    job.version += 1
    db.add(
        ReceiptReadReservation(
            user_id=claim.user_id,
            job_id=job.id,
            dispatch_token=job.dispatch_token,
            usage_date=day,
            image_pixels=prepared.pixel_upper_bound,
            image_bytes=len(prepared.jpeg),
            output_token_limit=config.max_output_tokens,
            response_byte_limit=config.max_response_bytes,
            outcome="unknown",
        )
    )
    await log_event(
        db,
        claim.user_id,
        "receipt_read_job",
        str(job.id),
        "dispatched",
        new_state={
            "generation": job.generation,
            "policy_epoch": job.policy_epoch,
            "pixel_upper_bound": prepared.pixel_upper_bound,
            "image_bytes": len(prepared.jpeg),
        },
        performed_by="system",
    )
    await db.flush()
    return True


async def finish_receipt_read(
    db: AsyncSession,
    claim: ReceiptReadClaim,
    outcome: ReceiptReadProviderOutcome,
    prepared: ReceiptReadPrepared,
    *,
    now: datetime,
    config: ReceiptReadConfig,
) -> None:
    job, source = await _locked_read(db, claim.job_id, config)
    if not job:
        return
    reservation = await db.scalar(
        select(ReceiptReadReservation)
        .where(
            ReceiptReadReservation.job_id == job.id,
            ReceiptReadReservation.dispatch_token == claim.lease_token,
        )
        .with_for_update()
    )
    if reservation:
        reservation.input_tokens = outcome.input_tokens
        reservation.output_tokens = outcome.output_tokens
        reservation.outcome = (
            "unknown" if outcome.uncertain else "error" if outcome.error_code else "success"
        )
    if source is None or job.state != "dispatched" or job.dispatch_token != claim.lease_token:
        return
    if not _claim_matches(job, claim, now):
        _terminal(job, "unknown", "receipt_read_result_unknown")
        return
    if outcome.payload is None or outcome.error_code:
        _terminal(
            job,
            "unknown" if outcome.uncertain else "failed",
            outcome.error_code or "invalid_model_output",
        )
        return
    validate_receipt_read_intake(outcome.payload, config)
    proposal = build_receipt_read_proposal(outcome.payload)
    quality = (
        "unsupported"
        if not proposal.importable
        else "partial"
        if proposal.problems
        or any(l.amount_minor is None or not l.name.strip() for l in proposal.body.lines)
        else "complete"
    )
    payload = outcome.payload.model_dump(mode="json")
    db.add(
        ReceiptReadExtraction(
            user_id=job.user_id,
            job_id=job.id,
            bill_id=job.bill_id,
            document_id=job.document_id,
            source_sha256=job.source_sha256,
            derivative_sha256=prepared.derivative_sha256,
            header_sha256=job.header_sha256,
            payload_sha256=digest(payload),
            payload_json=payload,
            proposal_json=proposal.model_dump(mode="json"),
            problems_json=[p.model_dump(mode="json") for p in proposal.problems],
            quality=quality,
            provider=config.provider,
            model=config.model,
            prompt_version=config.prompt_version,
            schema_version=config.schema_version,
            normalizer_version=config.normalizer_version,
            configuration_fingerprint=config.configuration_fingerprint,
            policy_epoch=job.policy_epoch,
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
        )
    )
    _terminal(job, "succeeded")
    await log_event(
        db,
        claim.user_id,
        "receipt_read_job",
        str(job.id),
        "succeeded",
        new_state={
            "generation": job.generation,
            "quality": quality,
            "policy_epoch": job.policy_epoch,
        },
        performed_by="system",
    )
    await db.flush()


async def fail_receipt_read_preparation(
    db: AsyncSession,
    claim: ReceiptReadClaim,
    *,
    now: datetime,
    config: ReceiptReadConfig,
    retryable: bool,
) -> None:
    job, source = await _locked_read(db, claim.job_id, config)
    if (
        job is None
        or source is None
        or job.state != "preparing"
        or job.dispatch_token
        or not _claim_matches(job, claim, now)
    ):
        return
    retry = (
        retryable and job.prepare_attempts < settings.DOCUMENT_RECEIPT_ITEMS_PREPARE_MAX_ATTEMPTS
    )
    _terminal(
        job,
        "pending" if retry else "failed",
        "preparation_unavailable" if retryable else "invalid_image",
    )
    if retry:
        job.next_attempt_at = now + timedelta(
            seconds=settings.DOCUMENT_RECEIPT_ITEMS_PREPARE_RETRY_SECONDS
        )


async def recover_receipt_reads(db: AsyncSession, *, now: datetime, limit: int) -> list[uuid.UUID]:
    await receipt_read_admission(db)
    q = (
        select(
            ReceiptReadJob.id,
            ReceiptReadJob.document_id,
            ReceiptReadJob.user_id,
            ReceiptReadJob.stream_id,
        )
        .where(
            ReceiptReadJob.state.in_({"preparing", "dispatched"}),
            ReceiptReadJob.lease_expires_at <= now,
        )
        .order_by(ReceiptReadJob.document_id, ReceiptReadJob.stream_id, ReceiptReadJob.id)
        .limit(limit)
    )
    locators = (await db.execute(q)).all()
    pending = []
    for ident, document_id, owner, stream_id in locators:
        await owned_receipt_read_document(db, owner, document_id, lock=True)
        await db.scalar(
            select(ReceiptReadStream).where(ReceiptReadStream.id == stream_id).with_for_update()
        )
        job = await db.scalar(
            select(ReceiptReadJob)
            .where(ReceiptReadJob.id == ident)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            not job
            or job.state not in {"preparing", "dispatched"}
            or not job.lease_expires_at
            or job.lease_expires_at > now
        ):
            continue
        if job.dispatch_token:
            _terminal(job, "unknown", "receipt_read_result_unknown")
        else:
            retry = job.prepare_attempts < settings.DOCUMENT_RECEIPT_ITEMS_PREPARE_MAX_ATTEMPTS
            _terminal(job, "pending" if retry else "failed", "preparation_expired")
            if retry:
                job.next_attempt_at = now + timedelta(
                    seconds=settings.DOCUMENT_RECEIPT_ITEMS_PREPARE_RETRY_SECONDS
                )
                pending.append(job.id)
    await db.flush()
    return pending
