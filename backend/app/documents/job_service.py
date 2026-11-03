"""Durable, short-transaction coordination for document processing jobs."""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, cast

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.documents.job_models import (
    DocumentProcessingJob,
    DocumentVisionPolicy,
    DocumentVisionUsage,
)
from app.documents.lifecycle import require_document_unarchived
from app.documents.models import Document, DocumentExtractionRevision
from app.documents.review_schemas import ReviewSuggestion
from app.documents.vision_config import VisionConfig, get_vision_config


@dataclass(frozen=True)
class JobClaim:
    job_id: uuid.UUID
    user_id: uuid.UUID
    document_id: uuid.UUID
    revision_id: uuid.UUID | None
    kind: Literal["vision", "local_ocr"]
    lease_token: uuid.UUID
    policy_epoch: int | None
    attempt_no: int


@dataclass(frozen=True)
class JobOutcome:
    suggestion: ReviewSuggestion | None = None
    warnings: tuple[str, ...] = ()
    source_sha256: str | None = None
    derivative_sha256: str | None = None
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    schema_version: str | None = None
    error_code: str | None = None
    retryable: bool = False
    completed: bool = False


def _terminalize_vision_document(document: Document) -> None:
    """A finished vision path requires human review, not more technical polling."""
    document.status = "done"


async def _admission_lock(db: AsyncSession) -> None:
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext('document-vision-admission'))"))


async def _locked_policy(db: AsyncSession) -> DocumentVisionPolicy | None:
    return (
        await db.execute(
            select(DocumentVisionPolicy).where(DocumentVisionPolicy.id == 1).with_for_update()
        )
    ).scalar_one_or_none()


async def create_vision_intent(
    db: AsyncSession, user_id: uuid.UUID, document_id: uuid.UUID, *, key: str
) -> DocumentProcessingJob:
    document = (
        await db.execute(
            select(Document)
            .where(Document.id == document_id, Document.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if document is None or not document.mime_type.startswith("image/"):
        raise LookupError("document_not_found")
    existing = (
        await db.execute(
            select(DocumentProcessingJob).where(
                DocumentProcessingJob.user_id == user_id,
                DocumentProcessingJob.kind == "vision",
                DocumentProcessingJob.intent_key == key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    require_document_unarchived(document)
    latest = (
        await db.execute(
            select(DocumentExtractionRevision)
            .where(DocumentExtractionRevision.document_id == document_id)
            .order_by(DocumentExtractionRevision.revision.desc())
            .limit(1)
            .with_for_update()
        )
    ).scalar_one_or_none()
    revision = DocumentExtractionRevision(
        user_id=user_id,
        document_id=document_id,
        revision=1 if latest is None else latest.revision + 1,
        status="pending",
        data={"document_type": "other", "fields": {}, "provenance": {}, "parser_version": None},
        field_provenance={},
        input_method="image",
    )
    db.add(revision)
    await db.flush()
    job = DocumentProcessingJob(
        user_id=user_id,
        document_id=document_id,
        revision_id=revision.id,
        kind="vision",
        intent_key=key,
        request_hash=hashlib.sha256(
            json.dumps({"document_id": str(document_id), "key": key}, sort_keys=True).encode()
        ).hexdigest(),
        state="pending",
    )
    db.add(job)
    await db.flush()
    return job


async def create_local_ocr_intent(
    db: AsyncSession, user_id: uuid.UUID, document_id: uuid.UUID, *, key: str
) -> DocumentProcessingJob:
    document = (
        await db.execute(
            select(Document)
            .where(Document.id == document_id, Document.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if document is None:
        raise LookupError("document_not_found")
    existing = (
        await db.execute(
            select(DocumentProcessingJob).where(
                DocumentProcessingJob.user_id == user_id,
                DocumentProcessingJob.kind == "local_ocr",
                DocumentProcessingJob.intent_key == key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    require_document_unarchived(document)
    active = await db.scalar(
        select(DocumentProcessingJob.id).where(
            DocumentProcessingJob.document_id == document_id,
            DocumentProcessingJob.state.in_(("pending", "processing")),
        )
    )
    if active is not None:
        raise ValueError("processing_active")
    job = DocumentProcessingJob(
        user_id=user_id,
        document_id=document_id,
        kind="local_ocr",
        intent_key=key,
        request_hash=hashlib.sha256(key.encode()).hexdigest(),
        state="pending",
    )
    db.add(job)
    await db.flush()
    return job


async def claim_processing_job(
    db: AsyncSession, job_id: uuid.UUID, *, now: datetime
) -> JobClaim | None:
    """Atomically claim a due job.  The caller commits before any filesystem or HTTP work."""
    await _admission_lock(db)
    policy = await _locked_policy(db)
    # Locate without a row lock solely to acquire the mandated document-before-job order.
    candidate = await db.get(DocumentProcessingJob, job_id)
    if candidate is None:
        return None
    document = (
        await db.execute(
            select(Document)
            .where(Document.id == candidate.document_id, Document.user_id == candidate.user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if document is None or document.archived_at is not None:
        return None
    job = (
        await db.execute(
            select(DocumentProcessingJob)
            .where(DocumentProcessingJob.id == job_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if (
        job is None
        or job.state not in {"pending", "processing"}
        or (job.next_attempt_at and job.next_attempt_at > now)
    ):
        return None
    revision = None
    if job.revision_id is not None:
        revision = (
            await db.execute(
                select(DocumentExtractionRevision)
                .where(DocumentExtractionRevision.id == job.revision_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if revision is None:
            job.state, job.error_code = "failed", "revision_missing"
            if job.kind == "vision":
                _terminalize_vision_document(document)
            return None
    if job.kind == "vision":
        if policy is None or not policy.enabled:
            job.state, job.error_code, job.lease_token, job.lease_expires_at = (
                "paused",
                "vision_disabled",
                None,
                None,
            )
            if revision is not None:
                revision.status, revision.error_code = "incomplete", "vision_disabled"
            if job.kind == "vision":
                _terminalize_vision_document(document)
            return None
        if job.state == "processing" and job.lease_expires_at and job.lease_expires_at > now:
            return None
        active = (
            await db.execute(
                select(func.count())
                .select_from(DocumentProcessingJob)
                .where(
                    DocumentProcessingJob.kind == "vision",
                    DocumentProcessingJob.state == "processing",
                    DocumentProcessingJob.lease_expires_at > now,
                )
            )
        ).scalar_one()
        if active >= settings.DOCUMENT_VISION_CONCURRENCY:
            return None
        max_attempts = settings.DOCUMENT_VISION_MAX_ATTEMPTS
    else:
        max_attempts = settings.DOCUMENT_MAX_ATTEMPTS
    if job.attempt_count >= max_attempts:
        job.state, job.error_code = "failed", "attempts_exhausted"
        if revision is not None:
            revision.status, revision.error_code = "incomplete", "attempts_exhausted"
        if job.kind == "vision":
            _terminalize_vision_document(document)
        return None
    token = uuid.uuid4()
    job.attempt_count += 1
    job.state, job.lease_token = "processing", token
    job.lease_expires_at = now + timedelta(
        seconds=settings.DOCUMENT_VISION_LEASE_SECONDS
        if job.kind == "vision"
        else settings.DOCUMENT_JOB_TIMEOUT_SECONDS
    )
    job.call_reserved_token = None
    job.policy_epoch = policy.epoch if job.kind == "vision" and policy else None
    job.error_code = None
    if revision is not None:
        revision.status, revision.error_code = "processing", None
    return JobClaim(
        job.id,
        job.user_id,
        job.document_id,
        job.revision_id,
        cast(Literal["vision", "local_ocr"], job.kind),
        token,
        job.policy_epoch,
        job.attempt_count,
    )


async def _reserve_usage(db: AsyncSession, claim: JobClaim, *, now: datetime) -> bool:
    statement = (
        insert(DocumentVisionUsage)
        .values(user_id=claim.user_id, usage_date=now.astimezone(UTC).date(), reserved_calls=1)
        .on_conflict_do_update(
            index_elements=(DocumentVisionUsage.user_id, DocumentVisionUsage.usage_date),
            set_={"reserved_calls": DocumentVisionUsage.reserved_calls + 1},
            where=DocumentVisionUsage.reserved_calls
            < settings.DOCUMENT_VISION_DAILY_CALL_LIMIT_PER_USER,
        )
        .returning(DocumentVisionUsage.user_id)
    )
    return (await db.execute(statement)).scalar_one_or_none() is not None


async def reserve_vision_call(
    db: AsyncSession, claim: JobClaim, *, now: datetime, config: VisionConfig
) -> bool:
    """Persist a single quota charge for this lease before crossing the HTTP boundary."""
    await _admission_lock(db)
    policy = await _locked_policy(db)
    document = (
        await db.execute(select(Document).where(Document.id == claim.document_id).with_for_update())
    ).scalar_one_or_none()
    job = (
        await db.execute(
            select(DocumentProcessingJob)
            .where(DocumentProcessingJob.id == claim.job_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    revision = (
        None
        if claim.revision_id is None
        else (
            await db.execute(
                select(DocumentExtractionRevision)
                .where(DocumentExtractionRevision.id == claim.revision_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
    )
    valid = bool(
        job
        and document
        and revision
        and policy
        and settings.DOCUMENT_VISION_ENABLED
        and policy.enabled
        and policy.epoch == claim.policy_epoch
        and policy.configuration_fingerprint == config.configuration_fingerprint
        and job.state == "processing"
        and job.lease_token == claim.lease_token
        and job.lease_expires_at
        and job.lease_expires_at > now
    )
    if not valid:
        if (
            job
            and document
            and revision
            and (not settings.DOCUMENT_VISION_ENABLED or not policy or not policy.enabled)
        ):
            job.state, job.error_code, job.lease_token, job.lease_expires_at = (
                "paused",
                "vision_disabled",
                None,
                None,
            )
            revision.status, revision.error_code = "incomplete", "vision_disabled"
            _terminalize_vision_document(document)
        elif (
            job
            and document
            and revision
            and policy
            and policy.configuration_fingerprint != config.configuration_fingerprint
        ):
            job.state, job.error_code = "paused", "vision_configuration_changed"
            revision.status, revision.error_code = "incomplete", "vision_configuration_changed"
            _terminalize_vision_document(document)
        return False
    assert job is not None and document is not None and revision is not None
    if job.call_reserved_token == claim.lease_token:
        return False
    try:
        reserved = await _reserve_usage(db, claim, now=now)
    except Exception:  # noqa: BLE001 - quota failures must fail closed regardless of driver error type.
        # Transaction callers roll back the failing counter operation; no provider call is allowed.
        return False
    if not reserved:
        job.state, job.error_code = "failed", "vision_daily_limit"
        revision.status, revision.error_code = "incomplete", "vision_daily_limit"
        _terminalize_vision_document(document)
        return False
    job.call_reserved_token = claim.lease_token
    return True


async def finish_processing_job(
    db: AsyncSession, claim: JobClaim, outcome: JobOutcome, *, now: datetime | None = None
) -> bool:
    now = now or datetime.now(UTC)
    await _admission_lock(db)
    policy = await _locked_policy(db)
    document = (
        await db.execute(select(Document).where(Document.id == claim.document_id).with_for_update())
    ).scalar_one_or_none()
    job = (
        await db.execute(
            select(DocumentProcessingJob)
            .where(DocumentProcessingJob.id == claim.job_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    revision = (
        None
        if claim.revision_id is None
        else (
            await db.execute(
                select(DocumentExtractionRevision)
                .where(DocumentExtractionRevision.id == claim.revision_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
    )
    if (
        not job
        or not document
        or job.state != "processing"
        or job.lease_token != claim.lease_token
        or job.lease_expires_at is None
        or job.lease_expires_at <= now
        or job.policy_epoch != claim.policy_epoch
        or (
            claim.kind == "vision"
            and (not policy or not policy.enabled or policy.epoch != claim.policy_epoch)
        )
    ):
        return False
    if claim.kind == "vision":
        current_config = get_vision_config(settings)
        if current_config is None:
            job.state, job.error_code, job.lease_token, job.lease_expires_at = (
                "failed",
                "configuration_missing",
                None,
                None,
            )
            if revision is not None:
                revision.status, revision.error_code = "incomplete", "configuration_missing"
            _terminalize_vision_document(document)
            return False
        if (
            not settings.DOCUMENT_VISION_ENABLED
            or policy is None
            or policy.configuration_fingerprint != current_config.configuration_fingerprint
        ):
            job.state, job.error_code = "paused", "vision_configuration_changed"
            if revision is not None:
                revision.status, revision.error_code = "incomplete", "vision_configuration_changed"
            _terminalize_vision_document(document)
            return False
    if revision is not None:
        latest = (
            await db.execute(
                select(DocumentExtractionRevision.id)
                .where(DocumentExtractionRevision.document_id == document.id)
                .order_by(DocumentExtractionRevision.revision.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest != revision.id:
            job.state, job.error_code = "superseded", "newer_revision"
            return False
    if outcome.suggestion is not None and revision is not None:
        revision.data = outcome.suggestion.model_dump(mode="json")
        revision.field_provenance = outcome.suggestion.provenance
        revision.parser_version = outcome.suggestion.parser_version
        revision.warnings = list(outcome.warnings)
        revision.source_sha256, revision.derivative_sha256 = (
            outcome.source_sha256,
            outcome.derivative_sha256,
        )
        revision.provider, revision.model = outcome.provider, outcome.model
        revision.prompt_version, revision.schema_version = (
            outcome.prompt_version,
            outcome.schema_version,
        )
        revision.status, revision.error_code = (
            ("ready" if not outcome.warnings else "incomplete"),
            outcome.error_code,
        )
        job.state, job.error_code = "succeeded", outcome.error_code
        document.status = "done"
        return True
    if claim.kind == "local_ocr" and outcome.completed:
        job.state, job.error_code = "succeeded", None
        document.status = "done"
        return True
    max_attempts = (
        settings.DOCUMENT_VISION_MAX_ATTEMPTS
        if claim.kind == "vision"
        else settings.DOCUMENT_MAX_ATTEMPTS
    )
    if outcome.retryable and job.attempt_count < max_attempts:
        delay = (
            settings.DOCUMENT_VISION_RETRY_DELAYS_SECONDS
            if claim.kind == "vision"
            else settings.DOCUMENT_RETRY_DELAYS_SECONDS
        )[job.attempt_count - 1]
        job.state, job.next_attempt_at, job.error_code = (
            "pending",
            now + timedelta(seconds=delay),
            outcome.error_code,
        )
        job.lease_token, job.lease_expires_at = None, None
        if revision is not None:
            revision.status, revision.error_code = "pending", outcome.error_code
    else:
        job.state, job.error_code = "failed", outcome.error_code or "processing_failed"
        if revision is not None:
            revision.status, revision.error_code = "incomplete", job.error_code
        if claim.kind == "vision":
            _terminalize_vision_document(document)
    return True


async def recover_processing_jobs(
    db: AsyncSession, *, now: datetime, limit: int
) -> list[uuid.UUID]:
    job_ids = list(
        (
            await db.execute(
                select(DocumentProcessingJob.id)
                .where(
                    DocumentProcessingJob.state == "processing",
                    DocumentProcessingJob.lease_expires_at <= now,
                )
                .order_by(DocumentProcessingJob.lease_expires_at)
                .limit(limit)
            )
        ).scalars()
    )
    ids: list[uuid.UUID] = []
    for job_id in job_ids:
        await _admission_lock(db)
        await _locked_policy(db)
        candidate = await db.get(DocumentProcessingJob, job_id)
        if candidate is None:
            continue
        document = (
            await db.execute(
                select(Document).where(Document.id == candidate.document_id).with_for_update()
            )
        ).scalar_one_or_none()
        if document is None or document.archived_at is not None:
            continue
        job = (
            await db.execute(
                select(DocumentProcessingJob)
                .where(DocumentProcessingJob.id == job_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if (
            job is None
            or job.state != "processing"
            or job.lease_expires_at is None
            or job.lease_expires_at > now
        ):
            continue
        revision = (
            None
            if job.revision_id is None
            else (
                await db.execute(
                    select(DocumentExtractionRevision)
                    .where(DocumentExtractionRevision.id == job.revision_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
        )
        max_attempts = (
            settings.DOCUMENT_VISION_MAX_ATTEMPTS
            if job.kind == "vision"
            else settings.DOCUMENT_MAX_ATTEMPTS
        )
        if job.attempt_count >= max_attempts:
            job.state, job.error_code = "failed", "attempts_exhausted"
            if revision is not None:
                revision.status, revision.error_code = "incomplete", "attempts_exhausted"
            if job.kind == "vision":
                _terminalize_vision_document(document)
        else:
            job.state, job.lease_token, job.lease_expires_at = "pending", None, None
            job.next_attempt_at = now
            if revision is not None:
                revision.status, revision.error_code = "pending", None
            ids.append(job.id)
    return ids
