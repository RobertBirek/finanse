"""Owner-scoped BO identity and ledger command. The caller owns the outer commit."""

import uuid
from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit.service import log_event
from app.finance.categorization_context import digest
from app.finance.dates import _local_today
from app.finance.document_guards import lock_document_mutations
from app.finance.ledger_validation import _validate_posting_sum
from app.finance.models import (
    Account,
    Category,
    FinanceCommandReceipt,
    FinancialTransaction,
    Posting,
)
from app.finance.opening_balance_models import AccountOpeningBalance
from app.finance.opening_balance_schemas import (
    MAX_MINOR,
    OpeningBalanceInput,
    OpeningBalanceUpdate,
    OpeningBalanceView,
)
from app.finance.queries import lock_accounts

SOURCE = "opening_balance"
ACTION = "update_opening_balance_v1"
HISTORY_MESSAGE = "BO jest zablokowany — konto ma inne transakcje."


def opening_values(currency: str, data: OpeningBalanceInput) -> tuple[int, int, Decimal]:
    """Validate before touching an account; arithmetic never uses floats."""
    data = OpeningBalanceInput.model_validate(data.model_dump(exclude={"expected_version"}))
    amount = abs(data.amount_minor)
    if currency == "PLN":
        if data.fx_rate is not None and data.fx_rate != 1:
            raise ValueError("BO w PLN wymaga kursu 1.")
        rate = Decimal(1)
    elif currency in {"EUR", "USD"}:
        if amount and data.fx_rate is None:
            raise ValueError("Niezerowy BO w walucie obcej wymaga kursu PLN.")
        rate = data.fx_rate or Decimal(1)
    else:
        raise ValueError("Unsupported currency")
    base = int((Decimal(amount) * rate).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
    if amount and (base < 1 or base > MAX_MINOR):
        raise ValueError("Wycena BO w PLN przekracza dozwolony zakres.")
    return amount, base, rate


async def _category(db: AsyncSession, owner: uuid.UUID) -> Category:
    row = await db.scalar(
        select(Category).where(Category.user_id == owner, Category.source == SOURCE)
    )
    if row is None:
        row = Category(user_id=owner, name="Bilans otwarcia", type="transfer", source=SOURCE)
        db.add(row)
        await db.flush()
    if row.type != "transfer" or not row.is_active:
        raise ValueError("Techniczna kategoria BO jest niespójna.")
    return row


async def _transaction(
    db: AsyncSession, owner: uuid.UUID, row: AccountOpeningBalance, account: Account
) -> FinancialTransaction | None:
    if row.transaction_id is None:
        return None
    txn = await db.scalar(
        select(FinancialTransaction)
        .where(FinancialTransaction.id == row.transaction_id, FinancialTransaction.user_id == owner)
        .options(selectinload(FinancialTransaction.postings))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    category = await _category(db, owner)
    if (
        txn is None
        or txn.type != SOURCE
        or txn.source != SOURCE
        or txn.is_pending
        or txn.date != row.opening_date
        or len(txn.postings) != 2
    ):
        raise ValueError("Zapis BO jest niespójny; nie można go zmienić.")
    legs = txn.postings
    if (
        sum(p.account_id == account.id and p.category_id is None for p in legs) != 1
        or sum(p.category_id == category.id and p.account_id is None for p in legs) != 1
        or any(
            p.is_budget_impact
            or p.source_currency != account.currency
            or p.source_amount <= 0
            or p.base_amount_pln <= 0
            for p in legs
        )
        or legs[0].source_amount != legs[1].source_amount
        or legs[0].fx_rate != legs[1].fx_rate
        or legs[0].direction == legs[1].direction
    ):
        raise ValueError("Postings BO są niespójne; nie można ich zmienić.")
    _validate_posting_sum(legs, SOURCE)
    return txn


async def _write_amount(
    db: AsyncSession,
    owner: uuid.UUID,
    account: Account,
    row: AccountOpeningBalance,
    data: OpeningBalanceInput,
) -> None:
    amount, base, rate = opening_values(account.currency, data)
    txn = await _transaction(db, owner, row, account)
    if not amount:
        if txn is not None:
            row.transaction_id = None
            await db.flush()
            await db.delete(txn)
            await db.flush()
        row.opening_date = data.date or _local_today()
        return
    category = await _category(db, owner)
    positive = data.amount_minor > 0
    if txn is None:
        txn = FinancialTransaction(
            user_id=owner,
            date=data.date or _local_today(),
            description="Bilans otwarcia",
            type=SOURCE,
            source=SOURCE,
            is_pending=False,
        )
        txn.postings = [
            Posting(account_id=account.id, category_id=None),
            Posting(category_id=category.id, account_id=None),
        ]
        db.add(txn)
    for posting in txn.postings:
        posting.source_amount = amount
        posting.base_amount_pln = base
        posting.source_currency = account.currency
        posting.fx_rate = float(rate)
        posting.fx_rate_source = "manual"
        posting.is_budget_impact = False
        posting.direction = "credit" if (posting.account_id is not None) == positive else "debit"
    _validate_posting_sum(txn.postings, SOURCE)
    txn.date = data.date or _local_today()
    await db.flush()
    row.transaction_id = txn.id
    row.opening_date = txn.date


async def initialize_opening_balance(
    db: AsyncSession,
    owner: uuid.UUID,
    account: Account,
    data: OpeningBalanceInput,
) -> None:
    row = AccountOpeningBalance(
        user_id=owner,
        account_id=account.id,
        opening_date=data.date or _local_today(),
    )
    db.add(row)
    await _write_amount(db, owner, account, row, data)
    await db.flush()
    if data.amount_minor:
        await log_event(
            db,
            owner,
            "account_opening_balance",
            str(account.id),
            "create_opening_balance",
            new_state=data.model_dump(mode="json"),
        )


async def attach_opening_balances(
    db: AsyncSession,
    owner: uuid.UUID,
    accounts: list[Account],
) -> None:
    """One bounded query for the supplied account set, including editability."""
    if not accounts:
        return
    row = AccountOpeningBalance
    has_history = exists(
        select(Posting.id)
        .where(
            Posting.account_id == row.account_id,
            Posting.transaction_id.is_distinct_from(row.transaction_id),
        )
        .correlate(row)
    )
    records = (
        await db.execute(
            select(row, Posting, has_history)
            .outerjoin(
                Posting,
                (Posting.transaction_id == row.transaction_id)
                & (Posting.account_id == row.account_id),
            )
            .where(row.user_id == owner, row.account_id.in_([a.id for a in accounts]))
        )
    ).all()
    views = {}
    for record, posting, history in records:
        if record.transaction_id is not None and posting is None:
            raise ValueError("Zapis BO jest niespójny.")
        views[record.account_id] = OpeningBalanceView(
            amount_minor=(
                posting.source_amount * (1 if posting.direction == "credit" else -1)
                if posting
                else 0
            ),
            date=record.opening_date,
            fx_rate=Decimal(str(posting.fx_rate)) if posting else None,
            version=record.version,
            can_edit=not history,
            blocked_reason=HISTORY_MESSAGE if history else None,
        )
    for account in accounts:
        account.opening_balance = views.get(account.id)


async def update_opening_balance(
    db: AsyncSession,
    owner: uuid.UUID,
    account_id: uuid.UUID,
    data: OpeningBalanceUpdate,
    idempotency_key: str,
) -> OpeningBalanceView:
    data = OpeningBalanceUpdate.model_validate(data.model_dump())
    if not idempotency_key.strip() or len(idempotency_key) > 255:
        raise ValueError("Nieprawidłowy klucz zapisu BO.")
    await lock_document_mutations(db, owner)
    account = (await lock_accounts(db, owner, {account_id}, exclusive=True)).get(account_id)
    if account is None:
        raise LookupError("Account not found")
    request_hash = digest({"account_id": account_id, **data.model_dump(mode="json")})
    receipt = await db.scalar(
        select(FinanceCommandReceipt).where(
            FinanceCommandReceipt.user_id == owner,
            FinanceCommandReceipt.action == ACTION,
            FinanceCommandReceipt.key == idempotency_key,
        )
    )
    if receipt is not None:
        if receipt.request_hash != request_hash:
            raise ValueError("Ten klucz zapisu BO dotyczy innego żądania.")
        return OpeningBalanceView.model_validate(receipt.response_json)
    row = await db.scalar(
        select(AccountOpeningBalance)
        .where(
            AccountOpeningBalance.user_id == owner, AccountOpeningBalance.account_id == account_id
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise ValueError("BO wymaga inicjalizacji; odśwież dane konta.")
    await attach_opening_balances(db, owner, [account])
    before = OpeningBalanceView.model_validate(account.opening_balance)
    if not before.can_edit:
        raise ValueError(HISTORY_MESSAGE)
    if row.version != data.expected_version:
        raise ValueError("Wersja BO zmieniła się; odśwież dane konta.")
    opening_values(account.currency, data)
    async with db.begin_nested():
        await _write_amount(db, owner, account, row, data)
        row.version += 1
        await db.flush()
        await attach_opening_balances(db, owner, [account])
        result = OpeningBalanceView.model_validate(account.opening_balance)
        await log_event(
            db,
            owner,
            "account_opening_balance",
            str(account_id),
            "update_opening_balance",
            old_state=before.model_dump(mode="json"),
            new_state=result.model_dump(mode="json"),
        )
        db.add(
            FinanceCommandReceipt(
                user_id=owner,
                action=ACTION,
                key=idempotency_key,
                request_hash=request_hash,
                entity_id=account_id,
                version=result.version,
                response_json=result.model_dump(mode="json"),
            )
        )
        await db.flush()
    return result
