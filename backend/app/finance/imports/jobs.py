"""Durable import intents, lease fencing and ordered publication; no ledger mutations."""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pydantic import TypeAdapter
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_event
from app.config import settings
from app.documents.models import Document
from app.finance.document_guards import lock_document_mutations
from app.finance.imports.contracts import ImportFailure, ParsedImport, ParsedStatement
from app.finance.imports.errors import ImportError
from app.finance.imports.models import (
    ImportBatch,
    ImportJob,
    ImportRevision,
    ImportRow,
    ImportSource,
)
from app.finance.imports.schemas import JobDTO
from app.finance.models import FinanceCommandReceipt

UNSUPPORTED = frozenset({"bank_unsupported", "layout_unsupported", "source_format_unsupported"})
PREPARE_ACTION = "prepare_bank_import"


@dataclass(frozen=True)
class ImportClaim:
    job_id: uuid.UUID
    owner_id: uuid.UUID
    batch_id: uuid.UUID
    source_id: uuid.UUID
    revision_id: uuid.UUID
    lease_token: uuid.UUID
    attempt: int


async def _source_context(
    db: AsyncSession,
    owner: uuid.UUID,
    source_id: uuid.UUID,
) -> tuple[ImportBatch, ImportSource, Document] | None:
    await lock_document_mutations(db, owner)
    batch_id = await db.scalar(
        select(ImportSource.batch_id).where(
            ImportSource.id == source_id,
            ImportSource.user_id == owner,
        )
    )
    if batch_id is None:
        return None
    batch = await db.scalar(
        select(ImportBatch)
        .where(
            ImportBatch.id == batch_id,
            ImportBatch.user_id == owner,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    source = await db.scalar(
        select(ImportSource)
        .where(
            ImportSource.id == source_id,
            ImportSource.user_id == owner,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if batch is None or source is None:
        return None
    document = await db.scalar(
        select(Document)
        .where(
            Document.id == source.document_id,
            Document.user_id == owner,
        )
        .execution_options(populate_existing=True)
    )
    if document is None:
        return None
    return batch, source, document


async def request_prepare(
    db: AsyncSession, owner: uuid.UUID, source_id: uuid.UUID, key: str
) -> JobDTO:
    if not key or len(key) > 255:
        raise ImportError("invalid_idempotency_key", "Nieprawidłowy klucz żądania.", 422)
    context = await _source_context(db, owner, source_id)
    if context is None:
        raise ImportError("source_not_found", "Nie znaleziono źródła.", 404)
    batch, source, document = context
    if batch.archived_at is not None:
        raise ImportError("import_archived", "Import jest zarchiwizowany.")
    if document.archived_at is not None:
        raise ImportError("document_archived", "Źródło jest zarchiwizowane.")
    digest = hashlib.sha256(str(source_id).encode()).hexdigest()
    receipt = await db.scalar(
        select(FinanceCommandReceipt).where(
            FinanceCommandReceipt.user_id == owner,
            FinanceCommandReceipt.action == PREPARE_ACTION,
            FinanceCommandReceipt.key == key,
        )
    )
    if receipt is not None:
        if receipt.request_hash != digest:
            raise ImportError("idempotency_key_reused", "Klucz należy do innego żądania.")
        job = await db.scalar(
            select(ImportJob).where(
                ImportJob.id == receipt.entity_id,
                ImportJob.user_id == owner,
                ImportJob.source_id == source_id,
            )
        )
        if job is None:
            raise RuntimeError("Durable import receipt has no job")
        return JobDTO.model_validate(job)
    job = await db.scalar(
        select(ImportJob)
        .where(
            ImportJob.user_id == owner,
            ImportJob.source_id == source_id,
            ImportJob.state.in_(("queued", "processing")),
        )
        .order_by(ImportJob.created_at.desc())
        .limit(1)
    )
    if job is None:
        number = (
            int(
                await db.scalar(
                    select(func.max(ImportRevision.number)).where(
                        ImportRevision.source_id == source_id,
                        ImportRevision.user_id == owner,
                    )
                )
                or 0
            )
            + 1
        )
        revision = ImportRevision(
            user_id=owner,
            source_id=source_id,
            batch_id=batch.id,
            number=number,
            source_sha256=document.sha256_hash,
        )
        db.add(revision)
        await db.flush([revision])
        job = ImportJob(
            user_id=owner, source_id=source_id, batch_id=batch.id, revision_id=revision.id
        )
        db.add(job)
        source.processing_state = "queued"
        source.validation_state = "needs_review"
        batch.version += 1
        await db.flush()
        await log_event(
            db,
            owner,
            "bank_import_job",
            str(job.id),
            "request_prepare",
            new_state={
                "source_id": str(source_id),
                "revision_id": str(revision.id),
                "sha256": document.sha256_hash,
            },
        )
    dto = JobDTO.model_validate(job)
    db.add(
        FinanceCommandReceipt(
            user_id=owner,
            action=PREPARE_ACTION,
            key=key,
            request_hash=digest,
            entity_id=job.id,
            response_json=dto.model_dump(mode="json"),
        )
    )
    await db.flush()
    return dto


def _due(now: datetime):
    return or_(
        and_(
            ImportJob.state == "queued",
            or_(ImportJob.next_attempt_at.is_(None), ImportJob.next_attempt_at <= now),
        ),
        and_(ImportJob.state == "processing", ImportJob.lease_expires_at <= now),
    )


async def claim_import_job(
    db: AsyncSession, job_id: uuid.UUID, now: datetime
) -> ImportClaim | None:
    if now.utcoffset() is None:
        raise ValueError("Import leases require an aware clock")
    job = await db.scalar(
        select(ImportJob)
        .where(
            ImportJob.id == job_id,
            _due(now),
            ImportJob.attempt < settings.FINANCE_IMPORT_MAX_ATTEMPTS,
        )
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    if job is None:
        return None
    job.state = "processing"
    job.attempt += 1
    job.lease_token = uuid.uuid4()
    job.lease_expires_at = now + timedelta(seconds=settings.FINANCE_IMPORT_LEASE_SECONDS)
    job.next_attempt_at = None
    job.error_code = None
    await db.flush([job])
    return ImportClaim(
        job.id,
        job.user_id,
        job.batch_id,
        job.source_id,
        job.revision_id,
        job.lease_token,
        job.attempt,
    )


async def _claim_context(
    db: AsyncSession,
    claim: ImportClaim,
) -> tuple[ImportBatch, ImportSource, Document, ImportRevision, ImportJob] | None:
    context = await _source_context(db, claim.owner_id, claim.source_id)
    if context is None:
        return None
    batch, source, document = context
    if batch.id != claim.batch_id:
        return None
    revision = await db.scalar(
        select(ImportRevision)
        .where(
            ImportRevision.id == claim.revision_id,
            ImportRevision.source_id == source.id,
            ImportRevision.batch_id == batch.id,
            ImportRevision.user_id == claim.owner_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    job = await db.scalar(
        select(ImportJob)
        .where(
            ImportJob.id == claim.job_id,
            ImportJob.user_id == claim.owner_id,
            ImportJob.source_id == source.id,
            ImportJob.revision_id == claim.revision_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if revision is None or job is None:
        return None
    if (
        job.state != "processing"
        or job.lease_token != claim.lease_token
        or job.attempt != claim.attempt
    ):
        return None
    return batch, source, document, revision, job


async def load_import_document(db: AsyncSession, claim: ImportClaim) -> tuple[Document, str] | None:
    """Detach immutable metadata. Caller commits/closes before reading or parsing any bytes."""
    context = await _claim_context(db, claim)
    if context is None:
        return None
    batch, source, document, _revision, job = context
    if batch.archived_at is not None or document.archived_at is not None:
        return None
    if job.lease_expires_at is None or job.lease_expires_at <= datetime.now(UTC):
        return None
    source.processing_state = "processing"
    await db.flush([source])
    db.expunge(document)
    return document, source.kind


async def finish_import_job(
    db: AsyncSession,
    claim: ImportClaim,
    result: ParsedImport | ImportFailure,
) -> bool:
    context = await _claim_context(db, claim)
    if context is None:
        return False
    batch, source, document, revision, job = context
    now = datetime.now(UTC)
    if batch.archived_at is not None or document.archived_at is not None:
        return False
    if job.lease_expires_at is None or job.lease_expires_at <= now:
        return False
    latest = await db.scalar(
        select(func.max(ImportRevision.number)).where(ImportRevision.source_id == source.id)
    )
    if latest != revision.number:
        return False
    if document.sha256_hash != revision.source_sha256:
        result = ImportFailure("source_integrity_failed", retryable=False)
    if isinstance(result, ImportFailure):
        retry = result.retryable and job.attempt < settings.FINANCE_IMPORT_MAX_ATTEMPTS
        job.state = "queued" if retry else "unsupported" if result.code in UNSUPPORTED else "error"
        job.error_code = result.code
        job.next_attempt_at = (
            now + timedelta(seconds=settings.FINANCE_IMPORT_RETRY_SECONDS * 2 ** (job.attempt - 1))
            if retry
            else None
        )
        revision.error_code = result.code
        source.processing_state = job.state
        source.validation_state = "needs_review" if retry else "blocked"
    else:
        parsed = TypeAdapter(ParsedImport).validate_python(result.model_dump(mode="json"))
        if parsed.kind != source.kind:
            raise ImportError("parser_kind_mismatch", "Parser zwrócił niewłaściwy rodzaj źródła.")
        # A successful current revision is authoritative even before its first
        # ledger evidence. Re-reading must not silently replace reviewed rows.
        is_reparse = source.current_revision_id is not None
        revision.result = parsed.model_dump(mode="json")
        revision.parser_version = parsed.parser_version
        revision.checks = [check.model_dump(mode="json") for check in parsed.checks]
        revision.warnings = [
            *parsed.warnings,
            *(["reparse_requires_comparison"] if is_reparse else []),
        ]
        revision.error_code = None
        for ordinal, row in enumerate(parsed.rows, 1):
            fields = row.model_dump(mode="json")
            key = (
                str(fields["key"])
                if isinstance(parsed, ParsedStatement)
                else str(fields["bank_number"])
            )
            db.add(
                ImportRow(
                    user_id=claim.owner_id,
                    batch_id=batch.id,
                    source_id=source.id,
                    revision_id=revision.id,
                    kind=source.kind,
                    ordinal=ordinal,
                    source_key=key,
                    row_hash=hashlib.sha256(
                        json.dumps(fields, sort_keys=True).encode()
                    ).hexdigest(),
                    fields=fields,
                )
            )
        if not is_reparse:
            source.current_revision_id = revision.id
            source.bank = parsed.bank
            source.layout = parsed.layout
            source.parser_version = parsed.parser_version
            source.currency = parsed.currency
            source.account_reference = (
                parsed.account_reference
                if isinstance(parsed, ParsedStatement)
                else parsed.loan_reference
            )
        blocked = any(check.required and check.result != "passed" for check in parsed.checks)
        source.validation_state = (
            "blocked" if blocked else "needs_review" if revision.warnings else "passed"
        )
        source.processing_state = "ready"
        job.state = "ready"
        job.error_code = "reparse_requires_comparison" if is_reparse else None
    job.lease_token = None
    job.lease_expires_at = None
    batch.version += 1
    await log_event(
        db,
        claim.owner_id,
        "bank_import_job",
        str(job.id),
        "finish_prepare",
        new_state={
            "source_id": str(source.id),
            "revision_id": str(revision.id),
            "state": job.state,
            "validation_state": source.validation_state,
            "error_code": job.error_code,
        },
    )
    await db.flush()
    return True


async def recover_import_jobs(db: AsyncSession, now: datetime) -> list[uuid.UUID]:
    """Bounded recovery with no job lock held while waiting for an owner mutation lock."""
    records = (
        (
            await db.execute(
                select(ImportJob)
                .join(ImportBatch, ImportBatch.id == ImportJob.batch_id)
                .join(ImportSource, ImportSource.id == ImportJob.source_id)
                .join(Document, Document.id == ImportSource.document_id)
                .where(_due(now), ImportBatch.archived_at.is_(None), Document.archived_at.is_(None))
                .order_by(ImportJob.created_at, ImportJob.id)
                .limit(settings.FINANCE_IMPORT_DISPATCH_BATCH)
            )
        )
        .scalars()
        .all()
    )
    ids = []
    for job in records:
        if job.attempt < settings.FINANCE_IMPORT_MAX_ATTEMPTS:
            ids.append(job.id)
            continue
        if job.lease_token is None:
            continue
        claim = ImportClaim(
            job.id,
            job.user_id,
            job.batch_id,
            job.source_id,
            job.revision_id,
            job.lease_token,
            job.attempt,
        )
        context = await _claim_context(db, claim)
        if context is None:
            break
        batch, source, _document, revision, locked = context
        if locked.lease_expires_at is None or locked.lease_expires_at > now:
            break
        locked.state = "error"
        locked.error_code = "attempts_exhausted"
        locked.lease_token = None
        locked.lease_expires_at = None
        revision.error_code = "attempts_exhausted"
        source.processing_state = "error"
        source.validation_state = "blocked"
        batch.version += 1
        await log_event(
            db,
            claim.owner_id,
            "bank_import_job",
            str(locked.id),
            "attempts_exhausted",
            new_state={"revision_id": str(revision.id)},
        )
        # At most one exhausted publication per transaction: do not retain this
        # job lock while waiting for a different owner's mutex on another iteration.
        break
    await db.flush()
    return ids
