"""Explicit document-payment allocation; ledger writes are limited to confirmed new expenses."""

import uuid
from datetime import date, timedelta

from sqlalchemy import String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit.service import log_event
from app.config import settings
from app.finance.bills import _response, _run_bill_command
from app.finance.bills_schemas import (
    AllocationCreate,
    BillCandidate,
    BillCandidatePage,
    BillPaymentCreate,
    BillResponse,
    MutationContext,
)
from app.finance.dates import _add_month, _local_today
from app.finance.document_guards import lock_document_mutations
from app.finance.models import (
    Account,
    DocumentPaymentAllocation,
    FinanceSettings,
    FinancialDocument,
    FinancialDocumentSource,
    FinancialTransaction,
    LoanPaymentLink,
    Posting,
    RecurringOccurrenceCoverage,
    ScheduledFinanceItem,
)
from app.finance.schemas import PostingCreate, TransactionCreate
from app.finance.transactions import create_transaction
from app.inbox.models import InboxItem


def _eligible(transaction: FinancialTransaction, posting: Posting) -> bool:
    account_debits = [
        item for item in transaction.postings if item.account_id and item.direction == "debit"
    ]
    return (
        transaction.type == "expense"
        and not transaction.is_pending
        and transaction.date <= _local_today()
        and len(transaction.postings) >= 2
        and sum(
            item.base_amount_pln if item.direction == "debit" else -item.base_amount_pln
            for item in transaction.postings
        )
        == 0
        and len(account_debits) == 1
        and account_debits[0].id == posting.id
        and posting.source_currency == "PLN"
        and posting.source_amount > 0
        and posting.source_amount == posting.base_amount_pln
        and str(posting.fx_rate) == "1.000000"
    )


async def _locked_bill(
    db: AsyncSession, user_id: uuid.UUID, bill_id: uuid.UUID
) -> FinancialDocument:
    bill = (
        await db.execute(
            select(FinancialDocument)
            .where(FinancialDocument.id == bill_id, FinancialDocument.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if bill is None:
        raise LookupError("bill_not_found")
    if bill.review != "approved" or bill.lifecycle != "active" or bill.currency != "PLN":
        raise ValueError("bill_not_allocatable")
    return bill


async def _locked_payment(
    db: AsyncSession, user_id: uuid.UUID, posting_id: uuid.UUID
) -> tuple[FinancialTransaction, Posting]:
    transaction = (
        await db.execute(
            select(FinancialTransaction)
            .join(Posting, Posting.transaction_id == FinancialTransaction.id)
            .where(FinancialTransaction.user_id == user_id, Posting.id == posting_id)
            .options(selectinload(FinancialTransaction.postings))
            .order_by(FinancialTransaction.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if transaction is None:
        raise LookupError("posting_not_found")
    postings = list(
        (
            await db.execute(
                select(Posting)
                .where(Posting.transaction_id == transaction.id)
                .order_by(Posting.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalars()
    )
    transaction.postings = postings
    posting = next((item for item in postings if item.id == posting_id), None)
    if posting is None or not _eligible(transaction, posting):
        raise ValueError("posting_not_eligible")
    linked = await db.scalar(
        select(LoanPaymentLink.id).where(LoanPaymentLink.transaction_id == transaction.id).limit(1)
    )
    if linked is not None:
        raise ValueError("posting_linked_to_loan")
    return transaction, posting


async def _allocated(db: AsyncSession, posting_id: uuid.UUID) -> int:
    return int(
        await db.scalar(
            select(func.coalesce(func.sum(DocumentPaymentAllocation.amount_minor), 0)).where(
                DocumentPaymentAllocation.posting_id == posting_id
            )
        )
        or 0
    )


async def _bill_paid(db: AsyncSession, bill_id: uuid.UUID) -> int:
    return int(
        await db.scalar(
            select(func.coalesce(func.sum(DocumentPaymentAllocation.amount_minor), 0)).where(
                DocumentPaymentAllocation.financial_document_id == bill_id
            )
        )
        or 0
    )


async def allocate_payment(
    db: AsyncSession,
    user_id: uuid.UUID,
    bill_id: uuid.UUID,
    data: AllocationCreate,
    *,
    context: MutationContext,
) -> BillResponse:
    async def operation() -> BillResponse:
        await lock_document_mutations(db, user_id)
        bill = await _locked_bill(db, user_id, bill_id)
        if bill.version != data.version:
            raise RuntimeError("version_conflict")
        _, posting = await _locked_payment(db, user_id, data.posting_id)
        conflicts = await _recurring_conflicts(db, user_id, bill, posting)
        if conflicts and data.confirm_recurring_conflict is not True:
            raise ValueError("recurring_conflict_confirmation_required")
        if await db.scalar(
            select(DocumentPaymentAllocation.id).where(
                DocumentPaymentAllocation.financial_document_id == bill.id,
                DocumentPaymentAllocation.posting_id == posting.id,
            )
        ):
            raise ValueError("allocation_already_exists")
        if data.amount_minor > (bill.total_minor or 0) - await _bill_paid(db, bill.id):
            raise ValueError("allocation_exceeds_bill_remaining")
        if data.amount_minor > posting.source_amount - await _allocated(db, posting.id):
            raise ValueError("allocation_exceeds_posting_capacity")
        db.add(
            DocumentPaymentAllocation(
                user_id=user_id,
                financial_document_id=bill.id,
                posting_id=posting.id,
                amount_minor=data.amount_minor,
            )
        )
        bill.version += 1
        await log_event(
            db,
            user_id,
            "financial_document",
            str(bill.id),
            "allocate_payment",
            new_state={
                "posting_id": str(posting.id),
                "amount_minor": data.amount_minor,
                "version": bill.version,
            },
            performed_by=context.performed_by,
        )
        await db.flush()
        return await _response(db, bill)

    return await _run_bill_command(
        db,
        user_id,
        "allocate_bill_payment",
        context.idempotency_key,
        {"bill_id": str(bill_id), **data.model_dump(mode="json")},
        operation,
    )


async def unlink_payment(
    db: AsyncSession,
    user_id: uuid.UUID,
    bill_id: uuid.UUID,
    allocation_id: uuid.UUID,
    expected_version: int,
    *,
    context: MutationContext,
) -> BillResponse:
    async def operation() -> BillResponse:
        await lock_document_mutations(db, user_id)
        bill = await _locked_bill(db, user_id, bill_id)
        if bill.version != expected_version:
            raise RuntimeError("version_conflict")
        allocation = (
            await db.execute(
                select(DocumentPaymentAllocation)
                .where(
                    DocumentPaymentAllocation.id == allocation_id,
                    DocumentPaymentAllocation.financial_document_id == bill.id,
                    DocumentPaymentAllocation.user_id == user_id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if allocation is None:
            raise LookupError("allocation_not_found")
        await _locked_payment(db, user_id, allocation.posting_id)
        await db.delete(allocation)
        bill.version += 1
        await log_event(
            db,
            user_id,
            "financial_document",
            str(bill.id),
            "unlink_payment",
            new_state={"allocation_id": str(allocation_id), "version": bill.version},
            performed_by=context.performed_by,
        )
        await db.flush()
        return await _response(db, bill)

    return await _run_bill_command(
        db,
        user_id,
        "unlink_bill_payment",
        context.idempotency_key,
        {
            "bill_id": str(bill_id),
            "allocation_id": str(allocation_id),
            "expected_version": expected_version,
        },
        operation,
    )


async def record_bill_payment(
    db: AsyncSession,
    user_id: uuid.UUID,
    bill_id: uuid.UUID,
    data: BillPaymentCreate,
    *,
    context: MutationContext,
) -> BillResponse:
    async def operation() -> BillResponse:
        await lock_document_mutations(db, user_id)
        bill = await _locked_bill(db, user_id, bill_id)
        if bill.version != data.version:
            raise RuntimeError("version_conflict")
        if data.payment_date > _local_today() or data.amount_minor > (
            bill.total_minor or 0
        ) - await _bill_paid(db, bill.id):
            raise ValueError("payment_not_allowed")
        account = await db.scalar(
            select(Account)
            .where(Account.id == data.account_id, Account.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if account is None:
            raise LookupError("account_not_found")
        if not account.is_active or account.currency != "PLN":
            raise ValueError("payment_account_not_eligible")
        transaction = await create_transaction(
            db,
            user_id,
            TransactionCreate(
                transaction_date=data.payment_date,
                description=data.description,
                type="expense",
                source="document_payment",
                postings=[
                    PostingCreate(
                        account_id=account.id,
                        source_amount=data.amount_minor,
                        source_currency="PLN",
                        base_amount_pln=data.amount_minor,
                        fx_rate=1,
                        direction="debit",
                    ),
                    PostingCreate(
                        category_id=data.category_id,
                        source_amount=data.amount_minor,
                        source_currency="PLN",
                        base_amount_pln=data.amount_minor,
                        fx_rate=1,
                        direction="credit",
                    ),
                ],
            ),
        )
        posting = next(item for item in transaction.postings if item.account_id == account.id)
        db.add(
            DocumentPaymentAllocation(
                user_id=user_id,
                financial_document_id=bill.id,
                posting_id=posting.id,
                amount_minor=data.amount_minor,
            )
        )
        bill.version += 1
        await log_event(
            db,
            user_id,
            "financial_document",
            str(bill.id),
            "record_payment",
            new_state={
                "transaction_id": str(transaction.id),
                "posting_id": str(posting.id),
                "amount_minor": data.amount_minor,
                "version": bill.version,
            },
            performed_by=context.performed_by,
        )
        await db.flush()
        return await _response(db, bill)

    return await _run_bill_command(
        db,
        user_id,
        "record_bill_payment",
        context.idempotency_key,
        {"bill_id": str(bill_id), **data.model_dump(mode="json")},
        operation,
    )


async def get_payment_candidates(
    db: AsyncSession,
    user_id: uuid.UUID,
    bill_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
    query: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    include_older: bool = False,
) -> BillCandidatePage:
    bill = await db.scalar(
        select(FinancialDocument).where(
            FinancialDocument.id == bill_id, FinancialDocument.user_id == user_id
        )
    )
    if bill is None:
        raise LookupError("bill_not_found")
    if bill.currency != "PLN":
        return BillCandidatePage(items=[], total=0, limit=limit, offset=offset)
    legacy_targets = {
        target
        for target in (
            await db.scalars(
                select(InboxItem.target_id)
                .join(
                    FinancialDocumentSource,
                    InboxItem.agent_suggestion["document_id"].astext
                    == cast(FinancialDocumentSource.document_id, String),
                )
                .where(
                    InboxItem.user_id == user_id,
                    InboxItem.target_type == "transaction",
                    FinancialDocumentSource.financial_document_id == bill_id,
                )
            )
        )
        if target is not None
    }
    transactions = list(
        (
            await db.execute(
                select(FinancialTransaction)
                .where(FinancialTransaction.user_id == user_id)
                .options(selectinload(FinancialTransaction.postings))
            )
        ).scalars()
    )
    reference_date = bill.due_date or bill.issue_date or _local_today()
    normalized_query = query.strip().lower() if query else None
    items: list[BillCandidate] = []
    for transaction in transactions:
        for posting in transaction.postings:
            if not _eligible(transaction, posting) or await db.scalar(
                select(LoanPaymentLink.id)
                .where(LoanPaymentLink.transaction_id == transaction.id)
                .limit(1)
            ):
                continue
            capacity = posting.source_amount - await _allocated(db, posting.id)
            if capacity <= 0:
                continue
            account = await db.get(Account, posting.account_id)
            legacy = transaction.id in legacy_targets
            if (date_from is not None and transaction.date < date_from) or (
                date_to is not None and transaction.date > date_to
            ):
                continue
            if normalized_query and normalized_query not in (
                f"{transaction.description} {account.name if account else ''}".lower()
            ):
                continue
            older_than_window = transaction.date < reference_date - timedelta(
                days=settings.BILL_PAYMENT_CANDIDATE_DATE_WINDOW_DAYS
            )
            if older_than_window and not (include_older or normalized_query or legacy):
                continue
            reasons = [
                "amount_exact"
                if posting.source_amount == bill.total_minor
                else "amount_difference",
                "date_older_than_window" if older_than_window else "date_within_window",
                "eligible_expense",
            ]
            if legacy:
                reasons.insert(0, "legacy_inbox_target")
            conflicts, forecast_before, forecast_after = await _recurring_conflict_effects(
                db, user_id, posting
            )
            items.append(
                BillCandidate(
                    transaction_id=transaction.id,
                    posting_id=posting.id,
                    date=transaction.date,
                    account=account.name if account else "",
                    amount_minor=posting.source_amount,
                    unallocated_minor=capacity,
                    reasons=reasons,
                    legacy_inbox_reference=str(transaction.id) if legacy else None,
                    recurring_conflicts=conflicts,
                    recurring_forecast_before_pln=forecast_before,
                    recurring_forecast_after_pln=forecast_after,
                )
            )
    items.sort(
        key=lambda item: (
            0 if item.legacy_inbox_reference else 1,
            abs(item.amount_minor - (bill.total_minor or 0)),
            abs((item.date - (bill.due_date or item.date)).days),
            str(item.transaction_id),
        )
    )
    return BillCandidatePage(
        items=items[offset : offset + limit], total=len(items), limit=limit, offset=offset
    )


async def _recurring_conflicts(
    db: AsyncSession, user_id: uuid.UUID, bill: FinancialDocument, posting: Posting
) -> list[str]:
    """A read-only warning; allocation still requires an explicit confirmation."""
    conflicts, _, _ = await _recurring_conflict_effects(db, user_id, posting)
    return conflicts


async def _recurring_conflict_effects(
    db: AsyncSession, user_id: uuid.UUID, posting: Posting
) -> tuple[list[str], int | None, int | None]:
    """Return forecast changes caused by allocating this actual payment.

    An allocation makes the transaction ineligible for the recurring actual matcher.
    Therefore these are occurrence-specific forecast values, not the posting amount.
    """
    if posting.account_id is None:
        return [], None, None
    transaction_date = await db.scalar(
        select(FinancialTransaction.date).where(FinancialTransaction.id == posting.transaction_id)
    )
    if transaction_date is None:
        return [], None, None
    categories = set(
        (
            await db.scalars(
                select(Posting.category_id).where(
                    Posting.transaction_id == posting.transaction_id,
                    Posting.category_id.is_not(None),
                )
            )
        ).all()
    )
    rows = list(
        (
            await db.scalars(
                select(ScheduledFinanceItem).where(
                    ScheduledFinanceItem.user_id == user_id,
                    ScheduledFinanceItem.is_active.is_(True),
                    ScheduledFinanceItem.type == "expense",
                    ScheduledFinanceItem.account_id == posting.account_id,
                    ScheduledFinanceItem.category_id.in_(categories),
                )
            )
        ).all()
    )
    today = _local_today()
    settings = await db.scalar(select(FinanceSettings).where(FinanceSettings.user_id == user_id))
    horizon_days = settings.forecast_horizon_days if settings is not None else 30
    grace_days = settings.overdue_grace_days if settings is not None else 3
    horizon_end = today + timedelta(days=horizon_days - 1)
    covered = set(
        (
            await db.execute(
                select(
                    RecurringOccurrenceCoverage.scheduled_item_id,
                    RecurringOccurrenceCoverage.occurrence_date,
                ).where(RecurringOccurrenceCoverage.user_id == user_id)
            )
        )
        .tuples()
        .all()
    )
    conflicts: list[str] = []
    before = 0
    after = 0
    month = date(today.year, today.month, 1)
    from app.finance.cashflow import _matching_actuals, _resolve_scheduled_amount

    while month <= horizon_end:
        for item in rows:
            due_date = date(month.year, month.month, item.due_day)
            if (
                due_date > horizon_end
                or due_date < today - timedelta(days=grace_days)
                or (item.id, due_date) in covered
            ):
                continue
            amount_before = await _resolve_scheduled_amount(db, user_id, item, today)
            if amount_before is None:
                continue
            current_matches = await _matching_actuals(
                db,
                user_id,
                item,
                start=due_date - timedelta(days=grace_days),
                end=due_date + timedelta(days=grace_days),
            )
            if not any(
                transaction.id == posting.transaction_id and amount == amount_before
                for transaction, amount in current_matches
            ):
                continue
            amount_after = await _resolve_scheduled_amount(
                db,
                user_id,
                item,
                today,
                exclude_transaction_ids={posting.transaction_id},
            )
            after_matches = (
                await _matching_actuals(
                    db,
                    user_id,
                    item,
                    start=due_date - timedelta(days=grace_days),
                    end=due_date + timedelta(days=grace_days),
                    exclude_transaction_ids={posting.transaction_id},
                )
                if amount_after is not None
                else []
            )
            conflicts.append(f"recurring:{item.id}:{due_date.isoformat()}")
            if amount_after is not None and not any(
                amount == amount_after for _, amount in after_matches
            ):
                after += amount_after
        month = _add_month(month)
    return conflicts, before, after
