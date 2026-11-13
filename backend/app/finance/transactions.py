"""Ledger mutations and FX conversion; transaction boundaries belong to callers."""

import uuid
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.finance.dates import _local_today
from app.finance.document_guards import guard_allocated_transaction_change, lock_document_mutations
from app.finance.ledger_validation import _validate_posting_sum, _validate_transaction_postings
from app.finance.models import FinancialTransaction, LoanPaymentLink, Posting
from app.finance.nbp_rates import NbpRateProvider
from app.finance.queries import get_accounts
from app.finance.schemas import ExchangeCreate, PostingCreate, TransactionCreate, TransactionUpdate
from app.finance.transaction_dates import (
    TransactionDateError,
    add_import_date_metadata,
    add_manual_date_metadata,
)
from app.work.service import validate_project_reference


async def create_transaction(
    db: AsyncSession,
    user_id: uuid.UUID,
    data: TransactionCreate,
    *,
    allow_category_reversal: bool = False,
    allow_inactive_accounts: bool = False,
) -> FinancialTransaction:
    """Stable public entrypoint for manual, import and existing integrations."""
    return await _create_transaction(
        db,
        user_id,
        data,
        allow_category_reversal=allow_category_reversal,
        allow_inactive_accounts=allow_inactive_accounts,
    )


async def create_card_refund_transaction(
    db: AsyncSession,
    user_id: uuid.UUID,
    data: TransactionCreate,
) -> FinancialTransaction:
    """Trusted card-service entrypoint; not a client-controlled ledger option."""
    return await _create_transaction(db, user_id, data, allow_card_refund=True)


async def _create_transaction(
    db: AsyncSession,
    user_id: uuid.UUID,
    data: TransactionCreate,
    *,
    allow_category_reversal: bool = False,
    allow_inactive_accounts: bool = False,
    allow_card_refund: bool = False,
    allow_bank_refund: bool = False,
    allow_manual_refund: bool = False,
    import_dates: tuple[date | None, date] | None = None,
) -> FinancialTransaction:
    # Only trusted import code explicitly opts into preserving source-category
    # reversals. Client-controlled `source` never disables validation.
    if allow_manual_refund and (
        data.source != "manual" or data.type != "expense" or data.is_pending
    ):
        raise ValueError("Manual refunds require the trusted posted expense correction path")
    if allow_category_reversal and data.source != "actual":
        raise ValueError("Category reversals require the explicit Actual import path")
    if allow_card_refund and (data.source != "credit_card" or data.type != "expense"):
        raise ValueError("Card refunds require the trusted expense correction path")
    if allow_inactive_accounts and data.source != "actual":
        raise ValueError("Inactive account history requires the explicit Actual import path")
    if allow_bank_refund and (
        data.source != "bank_import" or data.type != "expense" or import_dates is None
    ):
        raise ValueError("Bank refunds require the trusted bank-import path")
    if import_dates is not None and (
        data.source != "bank_import" or data.is_pending or data.transaction_date != import_dates[1]
    ):
        raise ValueError("Bank date evidence requires a new posted bank transaction")
    _validate_posting_sum(data.postings, data.type)
    await _validate_transaction_postings(
        db,
        user_id,
        data.postings,
        data.type,
        allow_category_reversal=allow_category_reversal,
        allow_inactive_accounts=allow_inactive_accounts,
        allow_card_refund=allow_card_refund,
        allow_bank_refund=allow_bank_refund,
        allow_manual_refund=allow_manual_refund,
    )
    await validate_project_reference(db, user_id, data.project_id)

    txn = FinancialTransaction(
        user_id=user_id,
        date=data.booking_date or data.transaction_date or _local_today(),
        description=data.description,
        type=data.type,
        is_pending=data.is_pending,
        project_id=data.project_id,
        source=data.source,
    )
    db.add(txn)
    if import_dates is not None:
        txn.id = uuid.uuid4()
        await add_import_date_metadata(db, txn, *import_dates)
    await db.flush()

    if data.booking_date is not None:
        await add_manual_date_metadata(db, txn, data.purchase_date, data.booking_date)

    for p_data in data.postings:
        posting = Posting(
            transaction_id=txn.id,
            account_id=p_data.account_id,
            category_id=p_data.category_id,
            source_amount=p_data.source_amount,
            source_currency=p_data.source_currency.upper(),
            base_amount_pln=p_data.base_amount_pln,
            fx_rate=p_data.fx_rate,
            fx_rate_source=p_data.fx_rate_source,
            direction=p_data.direction,
            is_budget_impact=p_data.is_budget_impact,
        )
        db.add(posting)

    await db.flush()

    result = await db.execute(
        select(FinancialTransaction)
        .options(selectinload(FinancialTransaction.postings))
        .where(FinancialTransaction.id == txn.id)
    )
    created = result.scalar_one()
    from app.finance.categorization_enrollment import observe_creation_policy
    from app.finance.rule_events import record_new_expense_event
    from app.finance.suggestion_jobs import record_new_suggestion_intent

    if (
        created.source == "manual"
        and not allow_manual_refund
        and created.type == "expense"
        and not created.is_pending
        and len(created.postings) == 2
    ):
        observation = await observe_creation_policy(db, user_id, created.description)
        await record_new_expense_event(db, user_id, created, observation=observation)
        await record_new_suggestion_intent(db, user_id, created, observation)
    return created


async def create_exchange_transaction(
    db: AsyncSession, user_id: uuid.UUID, data: ExchangeCreate
) -> FinancialTransaction:
    accounts = {account.id: account for account in await get_accounts(db, user_id)}

    from_account = accounts.get(data.from_account_id)
    to_account = accounts.get(data.to_account_id)
    if from_account is None or to_account is None:
        raise ValueError("Exchange account not found")
    if not from_account.is_active or not to_account.is_active:
        raise ValueError("Exchange account is not active")
    if from_account.id == to_account.id:
        raise ValueError("Exchange accounts must be different")

    from_currency = str(from_account.currency).upper()
    to_currency = str(to_account.currency).upper()
    if from_currency == to_currency:
        raise ValueError("Exchange accounts must have different currencies")
    if from_currency != "PLN" and to_currency != "PLN":
        raise ValueError("Cross-currency exchange is not supported")

    foreign_currency = from_currency if to_currency == "PLN" else to_currency
    effective_date = data.transaction_date or _local_today()

    if data.fx_rate is not None:
        rate = Decimal(str(data.fx_rate))
        rate_source = "manual"
    else:
        provider = NbpRateProvider()
        try:
            quote = await provider.get_rate(foreign_currency, effective_date)
        finally:
            await provider.close()
        if quote is None:
            raise ValueError(f"No FX rate available for {foreign_currency} on {effective_date}")
        rate = Decimal(str(quote.rate))
        rate_source = quote.source

    fx_rate_from = Decimal(1) if from_currency == "PLN" else rate
    fx_rate_to = Decimal(1) if to_currency == "PLN" else rate

    base = int(
        (Decimal(data.from_amount) * fx_rate_from).quantize(Decimal(1), rounding=ROUND_HALF_EVEN)
    )
    to_amount = int((Decimal(base) / fx_rate_to).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))

    return await create_transaction(
        db,
        user_id,
        TransactionCreate(
            transaction_date=effective_date,
            description=data.description,
            type="exchange",
            postings=[
                PostingCreate(
                    account_id=from_account.id,
                    source_amount=data.from_amount,
                    source_currency=from_currency,
                    base_amount_pln=base,
                    fx_rate=float(fx_rate_from),
                    fx_rate_source=rate_source,
                    direction="debit",
                ),
                PostingCreate(
                    account_id=to_account.id,
                    source_amount=to_amount,
                    source_currency=to_currency,
                    base_amount_pln=base,
                    fx_rate=float(fx_rate_to),
                    fx_rate_source=rate_source,
                    direction="credit",
                ),
            ],
        ),
    )


async def update_transaction(
    db: AsyncSession, user_id: uuid.UUID, transaction_id: uuid.UUID, data: TransactionUpdate
) -> FinancialTransaction | None:
    await lock_document_mutations(db, user_id)
    from app.finance.person_guards import guard_person_gift_change

    await guard_person_gift_change(
        db, user_id, transaction_id, set(data.model_dump(exclude_unset=True))
    )
    await guard_allocated_transaction_change(
        db, user_id, transaction_id, data.model_dump(exclude_unset=True)
    )
    txn = (
        await db.execute(
            select(FinancialTransaction)
            .where(
                FinancialTransaction.id == transaction_id, FinancialTransaction.user_id == user_id
            )
            .options(selectinload(FinancialTransaction.postings))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if txn is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    if "description" in update_data and update_data["description"] != txn.description:
        from app.finance.imports.models import ImportEvidence
        from app.finance.models import ActualImportMapping

        imported = (
            txn.source in {"actual", "bank_import"}
            or await db.scalar(
                select(ActualImportMapping.id)
                .where(
                    ActualImportMapping.entity_type == "transaction",
                    ActualImportMapping.entity_id == txn.id,
                )
                .limit(1)
            )
            is not None
            or await db.scalar(
                select(ImportEvidence.id)
                .where(
                    ImportEvidence.transaction_id == txn.id,
                )
                .limit(1)
            )
            is not None
        )
        if imported:
            raise ValueError(
                "Oryginalny opis importu jest chroniony. Użyj opisu i oznaczeń transakcji."
            )
    if (
        txn.date_metadata is not None
        and "transaction_date" in update_data
        and update_data["transaction_date"] != txn.date
    ):
        raise TransactionDateError(
            "date_editor_required",
            "Użyj korekty dat zakupu i księgowania, aby zachować ich znaczenie.",
        )
    if ("transaction_date" in update_data and update_data["transaction_date"] != txn.date) or (
        "is_pending" in update_data and update_data["is_pending"] != txn.is_pending
    ):
        from app.finance.credit_cards import guard_transaction

        await guard_transaction(db, user_id, transaction_id)
        linked = await db.scalar(
            select(LoanPaymentLink.id)
            .where(LoanPaymentLink.transaction_id == transaction_id)
            .limit(1)
        )
        if linked is not None:
            raise ValueError("Cannot change date or pending status of a linked loan payment")
    if any(
        update_data.get(key, True) is None
        for key in ("transaction_date", "description", "is_pending")
    ):
        raise ValueError("Transaction date, description and is_pending cannot be null")
    if "project_id" in update_data:
        await validate_project_reference(db, user_id, update_data["project_id"])
    if "transaction_date" in update_data:
        update_data["date"] = update_data.pop("transaction_date")
    for key, value in update_data.items():
        setattr(txn, key, value)
    await db.flush()
    await db.refresh(txn, attribute_names=["updated_at"])
    return txn


async def delete_transaction(
    db: AsyncSession, user_id: uuid.UUID, transaction_id: uuid.UUID
) -> bool:
    await lock_document_mutations(db, user_id)
    from app.finance.person_guards import guard_person_gift_change

    await guard_person_gift_change(db, user_id, transaction_id, {"delete"})
    await guard_allocated_transaction_change(db, user_id, transaction_id, {"delete": True})
    txn = (
        await db.execute(
            select(FinancialTransaction)
            .where(
                FinancialTransaction.id == transaction_id, FinancialTransaction.user_id == user_id
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if txn is None:
        return False
    from app.finance.credit_cards import guard_transaction

    await guard_transaction(db, user_id, transaction_id)
    if (
        await db.scalar(
            select(LoanPaymentLink.id)
            .where(LoanPaymentLink.transaction_id == transaction_id)
            .limit(1)
        )
        is not None
    ):
        raise ValueError("Cannot delete a linked loan payment")
    await db.delete(txn)
    await db.flush()
    return True
