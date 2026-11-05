"""Explicit adoption of immutable read evidence into a NEW human draft; no ledger writes."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.receipt_read_models import (
    ReceiptReadExtraction,
    ReceiptReadJob,
    ReceiptReadStream,
)
from app.documents.receipt_read_policy import receipt_read_admission
from app.documents.receipt_read_schemas import (
    ReceiptReadImport,
    ReceiptReadImportPreview,
    ReceiptReadImportPreviewRequest,
    ReceiptReadProposal,
)
from app.finance.categorization_context import CategorizationError, digest
from app.finance.receipt_commands import ReceiptCommandOutcome, run_receipt_command
from app.finance.receipt_items import append_receipt_revision, get_receipt_items
from app.finance.receipt_read_context import (
    ReceiptReadSource,
    load_receipt_read_source,
    owned_receipt_read_document,
)
from app.finance.receipt_read_evidence import derive_receipt_read_lineage, receipt_read_problems
from app.finance.receipt_schemas import ReceiptItemsContext, validate_receipt_input_limits


async def _preview(
    db: AsyncSession,
    owner: uuid.UUID,
    bill_id: uuid.UUID,
    data: ReceiptReadImportPreviewRequest,
    *,
    lock: bool,
) -> tuple[ReceiptReadSource, ReceiptReadExtraction, ReceiptReadImportPreview]:
    if lock:
        await receipt_read_admission(db)
    locator = await db.scalar(
        select(ReceiptReadJob)
        .where(
            ReceiptReadJob.user_id == owner,
            ReceiptReadJob.bill_id == bill_id,
            ReceiptReadJob.id == data.job_id,
        )
        .execution_options(populate_existing=True)
    )
    if not locator:
        raise LookupError("Odczyt nie istnieje.")
    document = await owned_receipt_read_document(db, owner, locator.document_id, lock=lock)
    if lock:
        await db.scalar(
            select(ReceiptReadStream)
            .where(ReceiptReadStream.id == locator.stream_id, ReceiptReadStream.user_id == owner)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        job = await db.scalar(
            select(ReceiptReadJob)
            .where(ReceiptReadJob.id == locator.id, ReceiptReadJob.user_id == owner)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    else:
        job = locator
    source = await load_receipt_read_source(db, owner, bill_id, document, lock=lock)
    extraction = await db.scalar(
        select(ReceiptReadExtraction)
        .where(
            ReceiptReadExtraction.user_id == owner,
            ReceiptReadExtraction.bill_id == bill_id,
            ReceiptReadExtraction.job_id == data.job_id,
        )
        .execution_options(populate_existing=True)
    )
    if not job or job.state != "succeeded" or not extraction:
        raise CategorizationError("read_not_ready", "Brak zaakceptowanego wyniku do przeniesienia.")
    if document.sha256_hash != extraction.source_sha256 or document.id != extraction.document_id:
        raise CategorizationError("read_source_changed", "Źródło odczytu zmieniło się.")
    ctx = source.items
    version = ctx.state.version if ctx.state else 0
    if version != data.expected_state_version:
        raise CategorizationError("version_conflict", "Pozycje paragonu zmieniły się.")
    proposal = ReceiptReadProposal.model_validate(extraction.proposal_json)
    if not proposal.importable or not proposal.body.lines:
        raise CategorizationError(
            "read_unsupported", "Ten wynik nie zawiera obsługiwanych pozycji paragonu PLN.", 422
        )
    proposal.problems = receipt_read_problems(extraction, source.header_sha256)
    try:
        validate_receipt_input_limits(proposal.body)
    except ValueError as error:
        raise CategorizationError(
            "receipt_limit", "Wynik przekracza bieżące limity importu.", 422
        ) from error
    snapshot = digest(
        {
            "owner": owner,
            "bill_id": bill_id,
            "document_id": document.id,
            "link_id": source.link.id,
            "source_sha256": document.sha256_hash,
            "header_sha256": source.header_sha256,
            "bill_version": source.bill.version,
            "state_version": version,
            "draft_id": ctx.draft.id if ctx.draft else None,
            "approved_id": ctx.approved.id if ctx.approved else None,
            "extraction_id": extraction.id,
            "extraction_sha256": extraction.payload_sha256,
            "proposal": proposal.model_dump(mode="json"),
        }
    )
    return (
        source,
        extraction,
        ReceiptReadImportPreview(
            job_id=job.id,
            extraction_id=extraction.id,
            payload_sha256=extraction.payload_sha256,
            bill_version=source.bill.version,
            state_version=version,
            import_snapshot=snapshot,
            will_replace_draft=ctx.draft is not None,
            proposal=proposal,
        ),
    )


async def preview_receipt_read_import(
    db: AsyncSession, owner: uuid.UUID, bill_id: uuid.UUID, data: ReceiptReadImportPreviewRequest
) -> ReceiptReadImportPreview:
    _, _, preview = await _preview(db, owner, bill_id, data, lock=False)
    return preview


async def import_receipt_read(
    db: AsyncSession,
    owner: uuid.UUID,
    bill_id: uuid.UUID,
    data: ReceiptReadImport,
    *,
    idempotency_key: str,
) -> ReceiptItemsContext:
    async def operation(receipt_id: uuid.UUID) -> ReceiptCommandOutcome:
        source, extraction, preview = await _preview(db, owner, bill_id, data, lock=True)
        if preview.import_snapshot != data.expected_import_snapshot:
            raise CategorizationError(
                "import_preview_changed", "Podgląd importu zmienił się. Sprawdź go ponownie."
            )
        body = preview.proposal.body.model_copy(deep=True)
        selected = source.items.draft or source.items.approved
        if selected:
            body.store_id, body.store_version = selected.body.store_id, selected.body.store_version
        keys = {line.line_key: uuid.uuid4() for line in body.lines}
        line_map = {str(keys[line.line_key]): int(line.line_key) - 1 for line in body.lines}
        discount_map = {}
        for line in body.lines:
            line.line_key = keys[line.line_key]
            line.category_id = None
            line.hint = None
        for discount in body.discounts:
            original = discount.discount_key
            discount.discount_key = uuid.uuid4()
            discount_map[str(discount.discount_key)] = int(original) - (1 << 64) - 1
            for share in discount.shares:
                share.line_key = keys[share.line_key]
        lineage = derive_receipt_read_lineage(
            None,
            extraction=extraction,
            body=body,
            header_sha256=source.header_sha256,
            line_map=line_map,
            discount_map=discount_map,
        )
        revision = await append_receipt_revision(
            db, source.items, body, kind="draft", receipt_id=receipt_id, lineage=lineage
        )
        response = await get_receipt_items(db, owner, bill_id)
        return ReceiptCommandOutcome(response, bill_id, response.state_version, [revision.id])

    return ReceiptItemsContext.model_validate(
        await run_receipt_command(
            db,
            owner,
            action="import_receipt_read",
            key=idempotency_key,
            payload={"bill_id": str(bill_id), **data.model_dump(mode="json")},
            operation=operation,
        )
    )
