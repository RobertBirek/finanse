"""Owned receipt evidence with batched category paths and semantic header validity."""

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.finance.categorization_context import columns, digest
from app.finance.models import Category, FinancialDocument
from app.finance.receipt_commands import receipt_locks
from app.finance.receipt_math import calculate_receipt
from app.finance.receipt_models import (
    ReceiptItemDiscount,
    ReceiptItemDiscountShare,
    ReceiptItemLine,
    ReceiptItemRevision,
    ReceiptItemState,
    ReceiptStore,
)
from app.finance.receipt_schemas import (
    ReceiptBody,
    ReceiptDiscountInput,
    ReceiptDiscountShareInput,
    ReceiptHistoryRef,
    ReceiptItemsContext,
    ReceiptLimits,
    ReceiptLineInput,
    ReceiptProblem,
    ReceiptRevisionView,
)
from app.finance.rule_policy import get_settings


def semantic_columns(row: Any) -> dict[str, Any]:
    return {
        k: v for k, v in columns(row).items() if k not in {"version", "created_at", "updated_at"}
    }


def receipt_header_sha256(bill: FinancialDocument) -> str:
    return digest(semantic_columns(bill))


def receipt_category_paths(
    categories: dict[uuid.UUID, Category], marker_id: uuid.UUID | None
) -> dict[uuid.UUID, tuple[str, str]]:
    result: dict[uuid.UUID, tuple[str, str]] = {}
    for target in categories.values():
        if target.id == marker_id:
            continue
        path = []
        seen = set()
        current: Category | None = target
        while current is not None:
            if (
                current.id in seen
                or not current.is_active
                or current.type != "expense"
                or current.user_id != target.user_id
            ):
                break
            seen.add(current.id)
            path.append(current)
            if current.parent_id and current.parent_id not in categories:
                break
            current = categories.get(current.parent_id) if current.parent_id else None
        else:
            result[target.id] = (
                " / ".join(c.name for c in reversed(path)),
                digest({"path": [semantic_columns(c) for c in reversed(path)]}),
            )
    return result


@dataclass
class ReceiptDomainContext:
    bill: FinancialDocument
    state: ReceiptItemState | None
    draft: ReceiptRevisionView | None
    approved: ReceiptRevisionView | None
    stores: dict[uuid.UUID, ReceiptStore]
    categories: dict[uuid.UUID, Category]
    marker_id: uuid.UUID | None
    path_hashes: dict[uuid.UUID, dict[uuid.UUID, str | None]] = field(default_factory=dict)


def receipt_blocked_reason(bill: FinancialDocument) -> str | None:
    return (
        None
        if bill.kind == "receipt"
        and bill.review == "approved"
        and bill.lifecycle == "active"
        and bill.currency == "PLN"
        else "receipt_not_editable"
    )


async def load_receipt_context(
    db: AsyncSession, owner: uuid.UUID, bill_id: uuid.UUID, *, lock: bool = False
) -> ReceiptDomainContext:
    if lock:
        await receipt_locks(db, owner)
    bill_query = (
        select(FinancialDocument)
        .where(FinancialDocument.id == bill_id, FinancialDocument.user_id == owner)
        .execution_options(populate_existing=True)
    )
    bill = await db.scalar(bill_query.with_for_update() if lock else bill_query)
    if not bill:
        raise LookupError("Paragon nie istnieje.")
    state_query = (
        select(ReceiptItemState)
        .where(ReceiptItemState.user_id == owner, ReceiptItemState.bill_id == bill_id)
        .execution_options(populate_existing=True)
    )
    state = await db.scalar(state_query.with_for_update() if lock else state_query)
    ids = (
        [i for i in (state.current_draft_revision_id, state.current_approved_revision_id) if i]
        if state
        else []
    )
    revisions = list(
        (
            await db.scalars(
                select(ReceiptItemRevision).where(
                    ReceiptItemRevision.user_id == owner,
                    ReceiptItemRevision.bill_id == bill_id,
                    ReceiptItemRevision.id.in_(ids),
                )
            )
        ).all()
    )
    store_query = (
        select(ReceiptStore)
        .where(
            ReceiptStore.user_id == owner,
            ReceiptStore.id.in_([r.store_id for r in revisions if r.store_id]),
        )
        .order_by(ReceiptStore.id)
        .execution_options(populate_existing=True)
    )
    stores = {
        s.id: s
        for s in (await db.scalars(store_query.with_for_update() if lock else store_query)).all()
    }
    categories = {
        c.id: c
        for c in (
            await db.scalars(
                select(Category)
                .where(Category.user_id == owner)
                .execution_options(populate_existing=True)
            )
        ).all()
    }
    policy = await get_settings(db, owner)
    ctx = ReceiptDomainContext(
        bill,
        state,
        None,
        None,
        stores,
        categories,
        policy.uncategorized_category_id if policy else None,
    )
    views = {}
    for revision in revisions:
        lines = (
            await db.scalars(
                select(ReceiptItemLine)
                .where(ReceiptItemLine.user_id == owner, ReceiptItemLine.revision_id == revision.id)
                .order_by(ReceiptItemLine.position)
            )
        ).all()
        discounts = (
            await db.scalars(
                select(ReceiptItemDiscount)
                .where(
                    ReceiptItemDiscount.user_id == owner,
                    ReceiptItemDiscount.revision_id == revision.id,
                )
                .order_by(ReceiptItemDiscount.position)
            )
        ).all()
        shares = (
            await db.scalars(
                select(ReceiptItemDiscountShare)
                .where(
                    ReceiptItemDiscountShare.user_id == owner,
                    ReceiptItemDiscountShare.revision_id == revision.id,
                )
                .order_by(ReceiptItemDiscountShare.line_key)
            )
        ).all()
        body = ReceiptBody(
            store_id=revision.store_id,
            store_version=revision.store_version,
            lines=[
                ReceiptLineInput(
                    line_key=l.line_key,
                    name=l.name,
                    amount_minor=l.amount_minor,
                    category_id=l.category_id,
                    hint=ReceiptHistoryRef.model_validate(l.hint_json) if l.hint_json else None,
                )
                for l in lines
            ],
            discounts=[
                ReceiptDiscountInput(
                    discount_key=d.discount_key,
                    name=d.name,
                    amount_minor=d.amount_minor,
                    shares=[
                        ReceiptDiscountShareInput(line_key=s.line_key, amount_minor=s.amount_minor)
                        for s in shares
                        if s.discount_key == d.discount_key
                    ],
                )
                for d in discounts
            ],
        )
        ctx.path_hashes[revision.id] = {l.line_key: l.category_path_sha256 for l in lines}
        view = ReceiptRevisionView(
            id=revision.id,
            sequence=revision.sequence,
            kind=cast(Literal["draft", "approved"], revision.kind),
            header_sha256=revision.header_sha256,
            body_sha256=revision.body_sha256,
            body=body,
            created_at=revision.created_at,
            current=True,
            problems=[],
        )
        view.problems = revision_problems(ctx, view)
        view.current = not view.problems
        views[revision.id] = view
    if state:
        ctx.draft = (
            views.get(state.current_draft_revision_id) if state.current_draft_revision_id else None
        )
        ctx.approved = (
            views.get(state.current_approved_revision_id)
            if state.current_approved_revision_id
            else None
        )
    return ctx


def revision_problems(ctx: ReceiptDomainContext, view: ReceiptRevisionView) -> list[ReceiptProblem]:
    problems = []

    def issue(code: str, message: str) -> None:
        problems.append(ReceiptProblem(code=code, message=message))

    if receipt_blocked_reason(ctx.bill):
        issue("receipt_not_editable", "Potrzebny aktywny zatwierdzony paragon PLN.")
    if view.header_sha256 != receipt_header_sha256(ctx.bill):
        issue("header_changed", "Nagłówek paragonu zmienił się; zatwierdź aktualne dane.")
    store = ctx.stores.get(view.body.store_id) if view.body.store_id else None
    if not store or not store.active or store.version != view.body.store_version:
        issue("store_changed", "Wybierz aktualny własny sklep.")
    paths = receipt_category_paths(ctx.categories, ctx.marker_id)
    calculation = calculate_receipt(view.body, expected_total_minor=ctx.bill.total_minor or 0)
    problems.extend(calculation.problems)
    nets = {r.line_key: r.net_minor for r in calculation.line_nets}
    for line in view.body.lines:
        if nets.get(line.line_key, 0) in (None, 0):
            continue
        if line.category_id not in paths:
            issue("invalid_category", "Wybierz aktywną własną kategorię i aktywną ścieżkę.")
        elif (
            view.kind == "approved"
            and ctx.path_hashes[view.id].get(line.line_key) != paths[line.category_id][1]
        ):
            issue("category_changed", "Ścieżka kategorii zmieniła się.")
    return problems


def receipt_context_response(ctx: ReceiptDomainContext) -> ReceiptItemsContext:
    current = ctx.draft or ctx.approved
    values = {
        n: getattr(settings, "FINANCE_RECEIPT_" + n.upper())
        for n in (
            "max_lines",
            "max_discounts",
            "max_discount_shares",
            "item_name_max_chars",
            "store_name_max_chars",
            "history_page_size",
            "history_prefix_min_chars",
        )
    }
    return ReceiptItemsContext(
        bill_id=ctx.bill.id,
        bill_version=ctx.bill.version,
        state_version=ctx.state.version if ctx.state else 0,
        editable=receipt_blocked_reason(ctx.bill) is None,
        blocked_reason=receipt_blocked_reason(ctx.bill),
        draft=ctx.draft,
        approved=ctx.approved,
        calculation=calculate_receipt(current.body, expected_total_minor=ctx.bill.total_minor or 0)
        if current
        else None,
        eligible_category_ids=list(receipt_category_paths(ctx.categories, ctx.marker_id)),
        limits=ReceiptLimits(**values),
    )
