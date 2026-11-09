from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.finance.bank_transactions import (
    BankPostingInput,
    BankTransactionInput,
    create_bank_transaction,
)
from app.finance.entities import create_account, create_category
from app.finance.models import TransactionDateMetadata
from app.finance.schemas import AccountCreate, CategoryCreate, PostingCreate, TransactionCreate
from app.finance.transactions import create_transaction

pytestmark = pytest.mark.integration


async def bank_input(db, owner, kind="expense_refund"):
    account = await create_account(db, owner, AccountCreate(name="Bank refund", type="checking"))
    category = await create_category(db, owner, CategoryCreate(name="Expense", type="expense"))
    postings = tuple(
        BankPostingInput(
            account_id=account.id if i == 0 else None,
            category_id=category.id if i == 1 else None,
            source_amount=100,
            source_currency="PLN",
            base_amount_pln=100,
            fx_rate=Decimal(1),
            fx_rate_source="pln",
            direction="credit" if i == 0 else "debit",
        )
        for i in range(2)
    )
    return BankTransactionInput(
        kind=kind,
        booking_date=date(2026, 1, 3),
        purchase_date=date(2026, 1, 2),
        description="Synthetic purchase refund",
        postings=postings,
    )


async def test_bank_refund_is_expense_credit_with_import_date_evidence(db_session, owner):
    data = await bank_input(db_session, owner.id)
    txn = await create_bank_transaction(db_session, owner.id, data)
    assert txn.type == "expense" and txn.source == "bank_import" and not txn.is_pending
    assert txn.date == date(2026, 1, 3)
    assert [(posting.source_amount, posting.direction) for posting in txn.postings] == [
        (100, "credit"),
        (100, "debit"),
    ]
    meta = await db_session.scalar(
        select(TransactionDateMetadata).where(TransactionDateMetadata.transaction_id == txn.id)
    )
    assert meta.purchase_date == date(2026, 1, 2) and meta.booking_date == txn.date
    assert meta.purchase_date_source == meta.booking_date_source == "import"


async def test_client_source_bank_import_does_not_enable_expense_reversal(db_session, owner):
    data = await bank_input(db_session, owner.id)
    with pytest.raises(ValueError, match="direction"):
        await create_transaction(
            db_session,
            owner.id,
            TransactionCreate(
                transaction_date=data.booking_date,
                description=data.description,
                type="expense",
                source="bank_import",
                postings=[PostingCreate(**posting.model_dump()) for posting in data.postings],
            ),
        )


async def test_actual_eur_usd_exchange_keeps_unequal_source_amounts(db_session, owner):
    accounts = [
        await create_account(
            db_session, owner.id, AccountCreate(name=currency, type="checking", currency=currency)
        )
        for currency in ["EUR", "USD"]
    ]
    postings = tuple(
        BankPostingInput(
            account_id=account.id,
            category_id=None,
            source_amount=amount,
            source_currency=account.currency,
            base_amount_pln=400,
            fx_rate=Decimal(rate),
            fx_rate_source=source,
            direction=direction,
        )
        for account, amount, rate, source, direction in zip(
            accounts,
            [100, 125],
            ["4", "3.2"],
            ["nbp", "bank_implied_cross"],
            ["debit", "credit"],
            strict=True,
        )
    )
    txn = await create_bank_transaction(
        db_session,
        owner.id,
        BankTransactionInput(
            kind="exchange",
            booking_date=date(2026, 1, 3),
            purchase_date=None,
            description="Actual FX",
            postings=postings,
        ),
    )
    assert txn.type == "exchange" and [posting.source_amount for posting in txn.postings] == [
        100,
        125,
    ]
    assert [posting.base_amount_pln for posting in txn.postings] == [400, 400]


@pytest.mark.parametrize(
    "change", [{"source_amount": 101}, {"base_amount_pln": 99}, {"fx_rate": "1.0000001"}]
)
async def test_trusted_path_never_bypasses_ledger_amount_or_precision_checks(
    db_session, owner, change
):
    data = await bank_input(db_session, owner.id)
    bad = BankPostingInput.model_validate(data.postings[0].model_dump() | change)
    with pytest.raises(ValueError):
        await create_bank_transaction(
            db_session, owner.id, data.model_copy(update={"postings": (bad, data.postings[1])})
        )
