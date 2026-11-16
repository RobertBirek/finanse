"""Only the dedicated command may edit BO; a zero net balance is not empty history."""

import uuid
from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.finance import service
from app.finance.models import Category, FinancialTransaction, Posting
from app.finance.schemas import (
    CategoryUpdate,
    PostingCreate,
    TransactionCreate,
    TransactionUpdate,
)
from tests.test_finance.test_opening_balances import (
    DAY,
    opening_account,
    owner_record,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def transfer(db, owner, first, second, *, pending=False):
    return await service.create_transaction(
        db,
        owner,
        TransactionCreate(
            type="transfer",
            description="[BO] lookalike",
            is_pending=pending,
            postings=[
                PostingCreate(
                    account_id=first.id, source_amount=100, base_amount_pln=100, direction="debit"
                ),
                PostingCreate(
                    account_id=second.id, source_amount=100, base_amount_pln=100, direction="credit"
                ),
            ],
        ),
    )


@pytest.mark.parametrize("pending", [True, False])
async def test_pending_and_net_zero_history_block_edit(db_session, pending):
    from app.finance.opening_balance_schemas import OpeningBalanceUpdate
    from app.finance.opening_balances import update_opening_balance

    owner = await owner_record(db_session)
    first = await opening_account(db_session, owner)
    second = await opening_account(db_session, owner)
    await transfer(db_session, owner, first, second, pending=pending)
    if not pending:
        await transfer(db_session, owner, second, first)
        assert (await service.get_account(db_session, owner, first.id)).balance_pln == 0
    account = await service.get_account(db_session, owner, first.id)
    assert not account.opening_balance.can_edit
    with pytest.raises(ValueError, match="transakc"):
        await update_opening_balance(
            db_session,
            owner,
            first.id,
            OpeningBalanceUpdate(amount_minor=0, date=DAY, expected_version=1),
            "blocked",
        )


async def test_only_linked_opening_is_excluded(db_session):
    from app.finance.opening_balance_schemas import OpeningBalanceUpdate
    from app.finance.opening_balances import update_opening_balance

    owner = await owner_record(db_session)
    account = await opening_account(db_session, owner)
    fake = FinancialTransaction(
        user_id=owner,
        description="Bilans otwarcia",
        type="opening_balance",
        source="opening_balance",
        date=DAY,
    )
    db_session.add(fake)
    await db_session.flush()
    db_session.add(
        Posting(
            transaction_id=fake.id,
            account_id=account.id,
            source_amount=100,
            base_amount_pln=100,
            source_currency="PLN",
            fx_rate=1,
            fx_rate_source="manual",
            direction="credit",
            is_budget_impact=False,
        )
    )
    await db_session.flush()
    with pytest.raises(ValueError, match="transakc"):
        await update_opening_balance(
            db_session,
            owner,
            account.id,
            OpeningBalanceUpdate(amount_minor=500, date=DAY, expected_version=1),
            "fake",
        )


async def test_opening_cannot_use_generic_transaction_or_category_paths(db_session):
    from app.finance.opening_balance_models import AccountOpeningBalance

    owner = await owner_record(db_session)
    account = await opening_account(db_session, owner, -125050)
    row = await db_session.scalar(
        select(AccountOpeningBalance).where(AccountOpeningBalance.account_id == account.id)
    )
    txn_id = row.transaction_id
    for change in [
        TransactionUpdate(description="Other"),
        TransactionUpdate(is_pending=True),
        TransactionUpdate(transaction_date=date(2026, 11, 15)),
    ]:
        with pytest.raises(ValueError, match="BO|otwarcia"):
            await service.update_transaction(db_session, owner, txn_id, change)
    with pytest.raises(ValueError, match="BO|otwarcia"):
        await service.delete_transaction(db_session, owner, txn_id)
    category = await db_session.scalar(select(Category).where(Category.source == "opening_balance"))
    with pytest.raises(ValueError, match="BO|otwarcia"):
        await service.update_category(
            db_session, owner, category.id, CategoryUpdate(name="Changed")
        )
    with pytest.raises(ValueError, match="BO|otwarcia"):
        await service.delete_category(db_session, owner, category.id)
    with pytest.raises(ValueError, match="BO|otwarcia"):
        await service.create_transaction(
            db_session,
            owner,
            TransactionCreate(
                type="transfer",
                description="Abuse category",
                postings=[
                    PostingCreate(
                        account_id=account.id,
                        source_amount=100,
                        base_amount_pln=100,
                        direction="credit",
                    ),
                    PostingCreate(
                        category_id=category.id,
                        source_amount=100,
                        base_amount_pln=100,
                        direction="debit",
                    ),
                ],
            ),
        )
    with pytest.raises(ValidationError):
        TransactionCreate(type="opening_balance", description="Forbidden", postings=[])
    assert (await service.get_account(db_session, owner, account.id)).balance_pln == -125050


async def test_other_owner_cannot_mutate_and_reserved_source_cannot_be_spoofed(db_session):
    from app.finance.opening_balance_schemas import OpeningBalanceUpdate
    from app.finance.opening_balances import update_opening_balance

    owner = await owner_record(db_session)
    account = await opening_account(db_session, owner)
    with pytest.raises(LookupError):
        await update_opening_balance(
            db_session,
            uuid.uuid4(),
            account.id,
            OpeningBalanceUpdate(amount_minor=100, date=DAY, expected_version=1),
            "foreign",
        )
    second = await opening_account(db_session, owner)
    data = TransactionCreate(
        type="transfer",
        source="opening_balance",
        description="Spoof",
        postings=[
            PostingCreate(
                account_id=account.id, source_amount=100, base_amount_pln=100, direction="credit"
            ),
            PostingCreate(
                account_id=second.id, source_amount=100, base_amount_pln=100, direction="debit"
            ),
        ],
    )
    with pytest.raises(ValueError, match="BO|otwarcia"):
        await service.create_transaction(db_session, owner, data)


async def test_dates_payment_gift_and_loan_paths_reject_opening(db_session):
    from app.finance.bill_payments import _locked_payment
    from app.finance.categorization_context import load_context
    from app.finance.loans import _valid_transfer_amount
    from app.finance.models import LoanAgreement
    from app.finance.opening_balance_models import AccountOpeningBalance
    from app.finance.person_context import get_person_link_context
    from app.finance.schemas import TransactionDatesUpdate
    from app.finance.transaction_dates import set_transaction_dates

    owner = await owner_record(db_session)
    account = await opening_account(db_session, owner, -125050)
    row = await db_session.scalar(
        select(AccountOpeningBalance).where(AccountOpeningBalance.account_id == account.id)
    )
    txn = await service.get_transaction(db_session, owner, row.transaction_id)
    leg = next(p for p in txn.postings if p.account_id == account.id)
    with pytest.raises(ValueError, match="eligible"):
        await _locked_payment(db_session, owner, leg.id)
    assert not (await get_person_link_context(db_session, owner, txn.id)).eligible
    with pytest.raises(ValueError, match="eligible"):
        _valid_transfer_amount(
            txn,
            LoanAgreement(
                user_id=owner,
                account_id=account.id,
                payment_account_id=account.id,
            ),
        )
    with pytest.raises(ValueError):
        await set_transaction_dates(
            db_session,
            owner,
            txn.id,
            TransactionDatesUpdate(
                purchase_date=None,
                booking_date=DAY,
                expected_version=0,
                expected_updated_at=txn.updated_at,
            ),
        )
    context = await load_context(db_session, owner, txn.id)
    assert not context.eligibility().allowed
