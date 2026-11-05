"""A human-approved product revision is evidence, not permission to touch the ledger."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.categorization_context import CategorizationError
from app.finance.receipt_commands import ReceiptCommandOutcome, run_receipt_command
from app.finance.receipt_context import (
    ReceiptDomainContext,
    load_receipt_context,
    receipt_header_sha256,
    revision_problems,
)
from app.finance.receipt_history import validate_receipt_history_refs
from app.finance.receipt_items import (
    append_receipt_revision,
    check_receipt_version,
    get_receipt_items,
)
from app.finance.receipt_read_evidence import derive_receipt_read_lineage
from app.finance.receipt_schemas import (
    ReceiptItemsApprove,
    ReceiptItemsContext,
    ReceiptProblem,
    ReceiptRevisionView,
)


def validate_approved_receipt(
    ctx: ReceiptDomainContext, revision: ReceiptRevisionView
) -> list[ReceiptProblem]:
    problems = revision_problems(ctx, revision)
    if (
        revision.kind != "approved"
        or not ctx.state
        or ctx.state.current_approved_revision_id != revision.id
    ):
        problems.append(
            ReceiptProblem(
                code="revision_changed", message="Zatwierdzona wersja pozycji zmieniła się."
            )
        )
    return problems


async def approve_receipt_items(
    db: AsyncSession,
    owner: uuid.UUID,
    bill_id: uuid.UUID,
    data: ReceiptItemsApprove,
    *,
    idempotency_key: str,
) -> ReceiptItemsContext:
    async def operation(receipt_id: uuid.UUID) -> ReceiptCommandOutcome:
        ctx = await load_receipt_context(db, owner, bill_id, lock=True)
        check_receipt_version(ctx, data.expected_version)
        draft = ctx.draft
        if (
            not draft
            or draft.id != data.draft_revision_id
            or draft.body_sha256 != data.expected_body_sha256
        ):
            raise CategorizationError("draft_changed", "Szkic zmienił się; wczytaj aktualne dane.")
        if not draft.current:
            raise CategorizationError(
                "incomplete_receipt", "Sprawdź produkty, kategorie, sklep i sumę paragonu.", 422
            )
        await validate_receipt_history_refs(db, owner, bill_id, draft.body)
        parent = ctx.lineages.get(draft.id)
        lineage = derive_receipt_read_lineage(
            parent,
            extraction=ctx.read_extractions.get(parent.extraction_id) if parent else None,
            body=draft.body,
            header_sha256=receipt_header_sha256(ctx.bill),
        )
        revision = await append_receipt_revision(
            db, ctx, draft.body, kind="approved", receipt_id=receipt_id, lineage=lineage
        )
        response = await get_receipt_items(db, owner, bill_id)
        return ReceiptCommandOutcome(response, bill_id, response.state_version, [revision.id])

    return ReceiptItemsContext.model_validate(
        await run_receipt_command(
            db,
            owner,
            action="approve_receipt_items",
            key=idempotency_key,
            payload={"bill_id": str(bill_id), **data.model_dump(mode="json")},
            operation=operation,
        )
    )
