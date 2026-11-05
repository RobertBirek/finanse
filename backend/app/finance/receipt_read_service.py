"""Human image-export consent and canonical job views, separate from financial approvals."""

import base64
import json
import uuid
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.documents.models import Document
from app.documents.receipt_read_config import ReceiptReadConfig, get_receipt_read_config
from app.documents.receipt_read_jobs import (
    admit_receipt_read,
    lock_receipt_read_stream,
    receipt_read_job_view,
)
from app.documents.receipt_read_models import (
    ReceiptReadExtraction,
    ReceiptReadJob,
    ReceiptReadStream,
    ReceiptReadUsage,
)
from app.documents.receipt_read_policy import (
    get_receipt_read_policy,
    receipt_read_admission,
    receipt_read_allowed,
    reconcile_receipt_read_policy,
)
from app.documents.receipt_read_schemas import (
    READ_ACTIVE_STATES,
    ReceiptReadCancel,
    ReceiptReadContext,
    ReceiptReadExportPreview,
    ReceiptReadJobPage,
    ReceiptReadJobView,
    ReceiptReadPreviewRequest,
    ReceiptReadProposal,
    ReceiptReadQuality,
    ReceiptReadResultView,
    ReceiptReadSourceView,
    ReceiptReadStart,
)
from app.finance.categorization_context import CategorizationError, digest
from app.finance.models import FinancialDocumentSource
from app.finance.receipt_commands import ReceiptCommandOutcome, run_receipt_command
from app.finance.receipt_context import load_receipt_context, receipt_blocked_reason
from app.finance.receipt_read_context import (
    READ_IMAGE_MIMES,
    ReceiptReadSource,
    load_receipt_read_source,
    owned_receipt_read_document,
)


def _cursor(value: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = json.loads(base64.urlsafe_b64decode(value))
        if (
            not isinstance(raw, list)
            or len(raw) != 2
            or not all(isinstance(value, str) for value in raw)
        ):
            raise ValueError("cursor")
        stamp = datetime.fromisoformat(raw[0])
        ident = uuid.UUID(raw[1])
        if stamp.tzinfo is None:
            raise ValueError("cursor")
        return stamp, ident
    except (ValueError, TypeError, IndexError) as error:
        raise CategorizationError(
            "invalid_cursor", "Nieprawidłowa strona odczytów.", 422
        ) from error


def _next_cursor(stamp: datetime, ident: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(json.dumps([stamp.isoformat(), str(ident)]).encode()).decode()


def receipt_read_limits() -> dict[str, int]:
    fields = {
        "max_edge": "MAX_EDGE",
        "max_bytes": "MAX_BYTES",
        "max_pixels": "MAX_PIXELS",
        "max_output_tokens": "MAX_OUTPUT_TOKENS",
        "max_response_bytes": "MAX_RESPONSE_BYTES",
        "daily_user_calls": "DAILY_CALL_LIMIT_PER_USER",
        "daily_global_calls": "DAILY_CALL_LIMIT_GLOBAL",
    }
    result = {
        name: int(getattr(settings, "DOCUMENT_RECEIPT_ITEMS_" + suffix))
        for name, suffix in fields.items()
    }
    result.update(
        max_lines=settings.FINANCE_RECEIPT_MAX_LINES,
        max_discounts=settings.FINANCE_RECEIPT_MAX_DISCOUNTS,
        max_discount_shares=settings.FINANCE_RECEIPT_MAX_DISCOUNT_SHARES,
        item_name_max_chars=settings.FINANCE_RECEIPT_ITEM_NAME_MAX_CHARS,
    )
    return result


async def get_receipt_read_context(
    db: AsyncSession, owner: uuid.UUID, bill_id: uuid.UUID, *, source_cursor: str | None = None
) -> ReceiptReadContext:
    ctx = await load_receipt_context(db, owner, bill_id)
    policy = await get_receipt_read_policy(db)
    config = get_receipt_read_config(settings)
    enabled = receipt_read_allowed(policy, config) and receipt_blocked_reason(ctx.bill) is None
    q = (
        select(Document)
        .join(FinancialDocumentSource, FinancialDocumentSource.document_id == Document.id)
        .where(
            Document.user_id == owner,
            FinancialDocumentSource.user_id == owner,
            FinancialDocumentSource.financial_document_id == bill_id,
        )
    )
    if source_cursor:
        q = q.where(tuple_(Document.created_at, Document.id) > _cursor(source_cursor))
    size = settings.DOCUMENT_RECEIPT_ITEMS_PAGE_SIZE
    rows = list(
        (await db.scalars(q.order_by(Document.created_at, Document.id).limit(size + 1))).all()
    )
    more = len(rows) > size
    rows = rows[:size]
    sources = []
    for d in rows:
        reason = (
            "source_archived"
            if d.archived_at
            else "image_required"
            if d.mime_type not in READ_IMAGE_MIMES
            else receipt_blocked_reason(ctx.bill)
        )
        sources.append(
            ReceiptReadSourceView(
                document_id=d.id,
                name=d.original_name,
                mime_type=d.mime_type,
                source_sha256=d.sha256_hash,
                allowed=reason is None,
                blocked_reason=reason,
            )
        )
    return ReceiptReadContext(
        bill_id=bill_id,
        bill_version=ctx.bill.version,
        state_version=ctx.state.version if ctx.state else 0,
        enabled=enabled,
        blocked_reason=None
        if enabled
        else "Odczyt wymaga aktywnego celu AI i zatwierdzonego aktywnego paragonu PLN.",
        policy_epoch=policy.epoch,
        provider=config.provider if config else None,
        model=config.model if config else None,
        limits=receipt_read_limits(),
        sources=sources,
        next_source_cursor=_next_cursor(rows[-1].created_at, rows[-1].id) if more else None,
    )


async def _export_preview(
    db: AsyncSession,
    owner: uuid.UUID,
    bill_id: uuid.UUID,
    data: ReceiptReadPreviewRequest,
    *,
    lock: bool,
) -> tuple[ReceiptReadSource, ReceiptReadConfig, ReceiptReadExportPreview]:
    config = get_receipt_read_config(settings)
    if lock:
        await receipt_read_admission(db)
    policy = (
        await reconcile_receipt_read_policy(db, config)
        if lock
        else await get_receipt_read_policy(db)
    )
    # Authorize ownership before feature gating, including foreign IDs while disabled.
    document = await owned_receipt_read_document(db, owner, data.document_id, lock=lock)
    if config is not None:
        stream, prior = await lock_receipt_read_stream(
            db, owner, bill_id, document.sha256_hash, config.configuration_fingerprint, lock=lock
        )
    else:
        stream, prior = None, None
    source = await load_receipt_read_source(db, owner, bill_id, document, lock=lock)
    if not receipt_read_allowed(policy, config) or config is None:
        raise CategorizationError(
            "receipt_read_disabled",
            "Odczyt produktów AI jest wyłączony lub konfiguracja zmieniła się.",
        )
    if document.size_bytes > settings.DOCUMENT_MAX_FILE_BYTES:
        raise CategorizationError("source_too_large", "Źródło przekracza bezpieczny limit.", 422)
    if data.reread_of_job_id and (
        not prior or prior.id != data.reread_of_job_id or prior.state in READ_ACTIVE_STATES
    ):
        raise CategorizationError(
            "read_generation_changed", "Wybierz aktualną zakończoną próbę przed ponownym odczytem."
        )
    token = digest(
        {
            "owner": owner,
            "bill_id": bill_id,
            "header": source.header_sha256,
            "document_id": document.id,
            "mime": document.mime_type,
            "source_sha256": document.sha256_hash,
            "link_id": source.link.id,
            "purpose": "receipt_items",
            "epoch": policy.epoch,
            "configuration_fingerprint": config.configuration_fingerprint,
            "consent_version": config.consent_version,
            "reread_of_job_id": data.reread_of_job_id,
            "stream_version": stream.version if data.reread_of_job_id and stream else None,
        }
    )
    remaining = []
    for scope, cap in [
        (f"user:{owner}", settings.DOCUMENT_RECEIPT_ITEMS_DAILY_CALL_LIMIT_PER_USER),
        ("global", settings.DOCUMENT_RECEIPT_ITEMS_DAILY_CALL_LIMIT_GLOBAL),
    ]:
        used = (
            await db.scalar(
                select(ReceiptReadUsage.reserved_calls).where(
                    ReceiptReadUsage.scope_key == scope,
                    ReceiptReadUsage.usage_date == datetime.now(UTC).date(),
                )
            )
            or 0
        )
        remaining.append(max(cap - used, 0))
    notice = "Do modelu trafi znormalizowana kopia całego obrazu, również widoczne dane osobowe i nagłówek. Odczyt produktów to dodatkowe płatne wywołanie względem odczytu nagłówka. Nie wyślemy danych kont ani katalogu kategorii."
    if data.reread_of_job_id:
        notice += (
            " Poprzednia próba mogła już naliczyć koszt. Nowa próba może oznaczać kolejny koszt."
        )
    preview = ReceiptReadExportPreview(
        document_id=document.id,
        source_sha256=document.sha256_hash,
        export_snapshot=token,
        policy_epoch=policy.epoch,
        provider=config.provider,
        model=config.model,
        reread_of_job_id=data.reread_of_job_id,
        limits=receipt_read_limits(),
        remaining_user_calls=remaining[0],
        remaining_global_calls=remaining[1],
        notice=notice,
    )
    return source, config, preview


async def preview_receipt_read_export(
    db: AsyncSession, owner: uuid.UUID, bill_id: uuid.UUID, data: ReceiptReadPreviewRequest
) -> ReceiptReadExportPreview:
    _, _, preview = await _export_preview(db, owner, bill_id, data, lock=False)
    return preview


async def start_receipt_read(
    db: AsyncSession,
    owner: uuid.UUID,
    bill_id: uuid.UUID,
    data: ReceiptReadStart,
    *,
    idempotency_key: str,
) -> ReceiptReadJobView:
    async def operation(receipt_id: uuid.UUID) -> ReceiptCommandOutcome:
        source, config, preview = await _export_preview(db, owner, bill_id, data, lock=True)
        if preview.export_snapshot != data.expected_export_snapshot:
            raise CategorizationError(
                "export_preview_changed", "Podgląd eksportu zmienił się. Sprawdź go ponownie."
            )
        job = await admit_receipt_read(
            db,
            owner,
            source,
            data,
            grant_receipt_id=receipt_id,
            config=config,
            now=datetime.now(UTC),
        )
        extraction_id = await db.scalar(
            select(ReceiptReadExtraction.id).where(
                ReceiptReadExtraction.job_id == job.id, ReceiptReadExtraction.user_id == owner
            )
        )
        return ReceiptCommandOutcome(
            receipt_read_job_view(job, extraction_id), bill_id, job.version, [job.id]
        )

    return ReceiptReadJobView.model_validate(
        await run_receipt_command(
            db,
            owner,
            action="start_receipt_read",
            key=idempotency_key,
            payload={"bill_id": str(bill_id), **data.model_dump(mode="json")},
            operation=operation,
        )
    )


async def cancel_receipt_read(
    db: AsyncSession,
    owner: uuid.UUID,
    bill_id: uuid.UUID,
    job_id: uuid.UUID,
    data: ReceiptReadCancel,
    *,
    idempotency_key: str,
) -> ReceiptReadJobView:
    async def operation(receipt_id: uuid.UUID) -> ReceiptCommandOutcome:
        await receipt_read_admission(db)
        locator = await db.scalar(
            select(ReceiptReadJob).where(
                ReceiptReadJob.id == job_id,
                ReceiptReadJob.user_id == owner,
                ReceiptReadJob.bill_id == bill_id,
            )
        )
        if locator is None:
            raise LookupError("Odczyt nie istnieje.")
        await owned_receipt_read_document(db, owner, locator.document_id, lock=True)
        await db.scalar(
            select(ReceiptReadStream)
            .where(ReceiptReadStream.id == locator.stream_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        job = await db.scalar(
            select(ReceiptReadJob)
            .where(ReceiptReadJob.id == job_id, ReceiptReadJob.user_id == owner)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        assert job is not None
        if job.dispatch_token:
            raise CategorizationError(
                "read_dispatched", "Rozpoczęto wysyłkę zdjęcia; nie można jej bezpiecznie cofnąć."
            )
        if job.state == "cancelled":
            return ReceiptCommandOutcome(receipt_read_job_view(job), bill_id, job.version, [job.id])
        if job.version != data.expected_version or job.state not in {"pending", "preparing"}:
            raise CategorizationError("read_changed", "Stan odczytu zmienił się.")
        job.state = "cancelled"
        job.version += 1
        job.lease_token = None
        job.lease_expires_at = None
        await db.flush()
        return ReceiptCommandOutcome(receipt_read_job_view(job), bill_id, job.version, [job.id])

    return ReceiptReadJobView.model_validate(
        await run_receipt_command(
            db,
            owner,
            action="cancel_receipt_read",
            key=idempotency_key,
            payload={
                "bill_id": str(bill_id),
                "job_id": str(job_id),
                **data.model_dump(mode="json"),
            },
            operation=operation,
        )
    )


async def list_receipt_reads(
    db: AsyncSession, owner: uuid.UUID, bill_id: uuid.UUID, *, cursor: str | None = None
) -> ReceiptReadJobPage:
    await load_receipt_context(db, owner, bill_id)
    q = (
        select(ReceiptReadJob, ReceiptReadExtraction.id)
        .outerjoin(
            ReceiptReadExtraction,
            (ReceiptReadExtraction.job_id == ReceiptReadJob.id)
            & (ReceiptReadExtraction.user_id == owner),
        )
        .where(ReceiptReadJob.user_id == owner, ReceiptReadJob.bill_id == bill_id)
    )
    if cursor:
        q = q.where(tuple_(ReceiptReadJob.created_at, ReceiptReadJob.id) < _cursor(cursor))
    size = settings.DOCUMENT_RECEIPT_ITEMS_PAGE_SIZE
    rows = list(
        (
            await db.execute(
                q.order_by(ReceiptReadJob.created_at.desc(), ReceiptReadJob.id.desc()).limit(
                    size + 1
                )
            )
        ).all()
    )
    more = len(rows) > size
    rows = rows[:size]
    return ReceiptReadJobPage(
        items=[receipt_read_job_view(j, e) for j, e in rows],
        next_cursor=_next_cursor(rows[-1][0].created_at, rows[-1][0].id) if more else None,
    )


async def get_receipt_read_job(
    db: AsyncSession, owner: uuid.UUID, bill_id: uuid.UUID, job_id: uuid.UUID
) -> ReceiptReadJobView:
    await load_receipt_context(db, owner, bill_id)
    job = await db.scalar(
        select(ReceiptReadJob)
        .where(
            ReceiptReadJob.id == job_id,
            ReceiptReadJob.user_id == owner,
            ReceiptReadJob.bill_id == bill_id,
        )
        .execution_options(populate_existing=True)
    )
    if not job:
        raise LookupError("Odczyt nie istnieje.")
    extraction_id = await db.scalar(
        select(ReceiptReadExtraction.id).where(
            ReceiptReadExtraction.user_id == owner,
            ReceiptReadExtraction.job_id == job_id,
            ReceiptReadExtraction.bill_id == bill_id,
        )
    )
    return receipt_read_job_view(job, extraction_id)


async def get_receipt_read_result(
    db: AsyncSession, owner: uuid.UUID, bill_id: uuid.UUID, job_id: uuid.UUID
) -> ReceiptReadResultView:
    job = await get_receipt_read_job(db, owner, bill_id, job_id)
    extraction = await db.scalar(
        select(ReceiptReadExtraction).where(
            ReceiptReadExtraction.user_id == owner,
            ReceiptReadExtraction.bill_id == bill_id,
            ReceiptReadExtraction.job_id == job_id,
        )
    )
    if not extraction:
        raise LookupError("Brak zapisanego wyniku odczytu.")
    return ReceiptReadResultView(
        job=job,
        extraction_id=extraction.id,
        payload_sha256=extraction.payload_sha256,
        proposal=ReceiptReadProposal.model_validate(extraction.proposal_json),
        payload=extraction.payload_json,
        source_sha256=extraction.source_sha256,
        derivative_sha256=extraction.derivative_sha256,
        provider=extraction.provider,
        model=extraction.model,
        prompt_version=extraction.prompt_version,
        schema_version=extraction.schema_version,
        quality=cast(ReceiptReadQuality, extraction.quality),
        created_at=extraction.created_at,
    )
