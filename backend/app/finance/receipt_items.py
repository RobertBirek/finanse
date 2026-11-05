"""Append/copy receipt bodies. Saving products never changes a financial posting."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.categorization_context import CategorizationError, columns, digest
from app.finance.receipt_commands import ReceiptCommandOutcome, run_receipt_command
from app.finance.receipt_context import (
    ReceiptDomainContext,
    load_receipt_context,
    receipt_blocked_reason,
    receipt_category_paths,
    receipt_context_response,
    receipt_header_sha256,
)
from app.finance.receipt_models import (
    ReceiptItemDiscount,
    ReceiptItemDiscountShare,
    ReceiptItemLine,
    ReceiptItemRevision,
    ReceiptItemState,
    ReceiptStore,
)
from app.finance.receipt_read_evidence import (
    ReceiptReadLineageData,
    derive_receipt_read_lineage,
    lineage_values,
)
from app.finance.receipt_read_models import ReceiptReadLineage
from app.finance.receipt_schemas import (
    ReceiptBody,
    ReceiptDraftSave,
    ReceiptItemsContext,
    ReceiptVersion,
    normalize_receipt_name,
)


def canonical_receipt_body(body: ReceiptBody) -> ReceiptBody:
    body = body.model_copy(deep=True)
    for d in body.discounts:
        d.shares.sort(key=lambda s: str(s.line_key))
    return body


async def append_receipt_revision(
    db: AsyncSession,
    ctx: ReceiptDomainContext,
    body: ReceiptBody,
    *,
    kind: str,
    receipt_id: uuid.UUID,
    lineage: ReceiptReadLineageData | None = None,
) -> ReceiptItemRevision:
    body = canonical_receipt_body(body)
    if ctx.state is None:
        ctx.state = ReceiptItemState(user_id=ctx.bill.user_id, bill_id=ctx.bill.id, version=1)
        db.add(ctx.state)
    else:
        ctx.state.version += 1
    state = ctx.state
    revision = ReceiptItemRevision(
        id=uuid.uuid4(),
        user_id=ctx.bill.user_id,
        bill_id=ctx.bill.id,
        sequence=state.version,
        kind=kind,
        store_id=body.store_id,
        store_version=body.store_version,
        header_sha256=receipt_header_sha256(ctx.bill),
        header_snapshot=columns(ctx.bill),
        body_sha256=digest(body.model_dump(mode="json")),
        parent_revision_id=state.current_draft_revision_id or state.current_approved_revision_id,
        command_receipt_id=receipt_id,
    )
    db.add(revision)
    await db.flush([revision])
    if lineage:
        db.add(
            ReceiptReadLineage(
                user_id=ctx.bill.user_id,
                bill_id=ctx.bill.id,
                item_revision_id=revision.id,
                **lineage_values(lineage),
            )
        )
    paths = receipt_category_paths(ctx.categories, ctx.marker_id)
    for position, line in enumerate(body.lines):
        db.add(
            ReceiptItemLine(
                user_id=ctx.bill.user_id,
                revision_id=revision.id,
                line_key=line.line_key,
                position=position,
                name=line.name,
                normalized_name=normalize_receipt_name(line.name),
                amount_minor=line.amount_minor,
                category_id=line.category_id,
                hint_json=line.hint.model_dump(mode="json") if line.hint else None,
                category_path_sha256=paths[line.category_id][1]
                if line.category_id in paths
                else None,
            )
        )
    for position, discount in enumerate(body.discounts):
        db.add(
            ReceiptItemDiscount(
                user_id=ctx.bill.user_id,
                revision_id=revision.id,
                discount_key=discount.discount_key,
                position=position,
                name=discount.name,
                amount_minor=discount.amount_minor,
            )
        )
    await db.flush()
    for d in body.discounts:
        for s in d.shares:
            db.add(
                ReceiptItemDiscountShare(
                    user_id=ctx.bill.user_id,
                    revision_id=revision.id,
                    discount_key=d.discount_key,
                    line_key=s.line_key,
                    amount_minor=s.amount_minor,
                )
            )
    if kind == "draft":
        state.current_draft_revision_id = revision.id
    else:
        state.current_approved_revision_id, state.current_draft_revision_id = revision.id, None
    await db.flush()
    return revision


def check_receipt_version(ctx: ReceiptDomainContext, version: int) -> None:
    if receipt_blocked_reason(ctx.bill):
        raise CategorizationError(
            "receipt_not_editable", "Potrzebny aktywny zatwierdzony paragon PLN.", 422
        )
    if (ctx.state.version if ctx.state else 0) != version:
        raise CategorizationError("version_conflict", "Pozycje paragonu zmieniły się.")


async def get_receipt_items(
    db: AsyncSession, owner: uuid.UUID, bill_id: uuid.UUID
) -> ReceiptItemsContext:
    return receipt_context_response(await load_receipt_context(db, owner, bill_id))


async def save_receipt_draft(
    db: AsyncSession,
    owner: uuid.UUID,
    bill_id: uuid.UUID,
    data: ReceiptDraftSave,
    *,
    idempotency_key: str,
) -> ReceiptItemsContext:
    async def operation(receipt_id: uuid.UUID) -> ReceiptCommandOutcome:
        from app.finance.receipt_schemas import validate_receipt_input_limits

        try:
            validate_receipt_input_limits(data.body)
        except ValueError as error:
            raise CategorizationError("receipt_limit", str(error), 422) from error
        ctx = await load_receipt_context(db, owner, bill_id, lock=True)
        check_receipt_version(ctx, data.expected_version)
        if ctx.bill.version != data.expected_bill_version:
            raise CategorizationError("version_conflict", "Nagłówek paragonu zmienił się.")
        if data.body.store_id:
            store = await db.get(ReceiptStore, data.body.store_id, populate_existing=True)
            if not store or store.user_id != owner:
                raise LookupError("Sklep nie istnieje.")
            if data.body.store_version is not None and store.version != data.body.store_version:
                raise CategorizationError("store_changed", "Sklep zmienił się.")
        if any(l.category_id and l.category_id not in ctx.categories for l in data.body.lines):
            raise LookupError("Kategoria nie istnieje.")
        from app.finance.receipt_history import validate_receipt_history_refs

        await validate_receipt_history_refs(db, owner, bill_id, data.body)
        parent_view = ctx.draft or ctx.approved
        parent = ctx.lineages.get(parent_view.id) if parent_view else None
        extraction = ctx.read_extractions.get(parent.extraction_id) if parent else None
        lineage = derive_receipt_read_lineage(
            parent,
            extraction=extraction,
            body=data.body,
            header_sha256=receipt_header_sha256(ctx.bill),
            review=data.extraction_review,
        )
        revision = await append_receipt_revision(
            db, ctx, data.body, kind="draft", receipt_id=receipt_id, lineage=lineage
        )
        response = await get_receipt_items(db, owner, bill_id)
        return ReceiptCommandOutcome(response, bill_id, response.state_version, [revision.id])

    result = await run_receipt_command(
        db,
        owner,
        action="save_receipt_draft",
        key=idempotency_key,
        payload={
            "bill_id": str(bill_id),
            **data.model_dump(
                mode="json",
                exclude={"extraction_review"} if data.extraction_review is None else set(),
            ),
        },
        operation=operation,
    )
    return ReceiptItemsContext.model_validate(result)


async def discard_receipt_draft(
    db: AsyncSession,
    owner: uuid.UUID,
    bill_id: uuid.UUID,
    data: ReceiptVersion,
    *,
    idempotency_key: str,
) -> ReceiptItemsContext:
    async def operation(receipt_id: uuid.UUID) -> ReceiptCommandOutcome:
        ctx = await load_receipt_context(db, owner, bill_id, lock=True)
        check_receipt_version(ctx, data.expected_version)
        if not ctx.state or not ctx.state.current_draft_revision_id:
            raise CategorizationError("no_draft", "Brak szkicu do odrzucenia.")
        ctx.state.current_draft_revision_id = None
        ctx.state.version += 1
        await db.flush()
        response = await get_receipt_items(db, owner, bill_id)
        return ReceiptCommandOutcome(response, bill_id, response.state_version, [])

    result = await run_receipt_command(
        db,
        owner,
        action="discard_receipt_draft",
        key=idempotency_key,
        payload={"bill_id": str(bill_id), **data.model_dump(mode="json")},
        operation=operation,
    )
    return ReceiptItemsContext.model_validate(result)
