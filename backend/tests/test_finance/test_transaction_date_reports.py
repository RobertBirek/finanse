from datetime import date

import pytest

from app.finance import service
from app.finance.schemas import (
    AccountCreate,
    CategoryBudgetCreate,
    CategoryCreate,
    PostingCreate,
    TransactionCreate,
    TransactionSearch,
)
from tests.test_finance.test_bill_payments import create_owner

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def split_expense(db, owner):
    account = await service.create_account(
        db, owner, AccountCreate(name="Synthetic bank", type="checking", currency="PLN")
    )
    food = await service.create_category(db, owner, CategoryCreate(name="Food", type="expense"))
    home = await service.create_category(db, owner, CategoryCreate(name="Home", type="expense"))
    await service.create_budget(
        db, owner, CategoryBudgetCreate(category_id=food.id, amount_pln=10000)
    )
    await service.create_budget(
        db, owner, CategoryBudgetCreate(category_id=home.id, amount_pln=10000)
    )
    txn = await service.create_transaction(
        db,
        owner,
        TransactionCreate(
            type="expense",
            description="Synthetic split",
            purchase_date=date(2026, 1, 30),
            booking_date=date(2026, 2, 2),
            postings=[
                PostingCreate(
                    account_id=account.id,
                    source_amount=10000,
                    base_amount_pln=10000,
                    direction="debit",
                ),
                PostingCreate(
                    category_id=food.id,
                    source_amount=8000,
                    base_amount_pln=8000,
                    direction="credit",
                ),
                PostingCreate(
                    category_id=home.id,
                    source_amount=2000,
                    base_amount_pln=2000,
                    direction="credit",
                ),
            ],
        ),
    )
    return txn, account, food, home


async def test_month_boundary_uses_purchase_for_expense_summary_not_booking(db_session):
    owner = await create_owner(db_session)
    _, account, _, _ = await split_expense(db_session, owner)
    jan = await service.get_financial_summary(db_session, owner, month=1, year=2026)
    feb = await service.get_financial_summary(db_session, owner, month=2, year=2026)
    assert jan.expense_total_pln == 10000
    assert feb.expense_total_pln == 0
    assert jan.balance_all_pln == feb.balance_all_pln == -10000
    assert (await service.get_account(db_session, owner, account.id)).balance_pln == -10000


async def test_split_category_and_budget_totals_roll_up_once_on_purchase_month(db_session):
    owner = await create_owner(db_session)
    _, _, food, home = await split_expense(db_session, owner)
    jan = await service.get_category_summary(db_session, owner, month=1, year=2026)
    feb = await service.get_category_summary(db_session, owner, month=2, year=2026)
    assert {x.category_id: x.total_pln for x in jan.categories} == {food.id: 8000, home.id: 2000}
    assert sum(x.total_pln for x in feb.categories) == 0
    budget = await service.get_budget_status(db_session, owner, month=1, year=2026)
    assert {x.category_id: x.spent_pln for x in budget.items} == {food.id: 8000, home.id: 2000}
    assert budget.total_spent_pln == 10000


async def test_bank_search_retains_booking_month_and_legacy_reports_keep_fallback(db_session):
    owner = await create_owner(db_session)
    txn, _, _, _ = await split_expense(db_session, owner)
    jan = await service.search_transactions(
        db_session, owner, TransactionSearch(date_from=date(2026, 1, 1), date_to=date(2026, 1, 31))
    )
    feb = await service.search_transactions(
        db_session, owner, TransactionSearch(date_from=date(2026, 2, 1), date_to=date(2026, 2, 28))
    )
    assert jan.total == 0 and [t.id for t in feb.items] == [txn.id]
    assert feb.items[0].date_metadata.purchase_date == date(2026, 1, 30)
    from tests.test_finance.test_transaction_search import seed

    legacy, _, _ = await seed(db_session, owner, amount=777, day=date(2026, 3, 5))
    assert legacy.date_metadata is None
    march = await service.get_financial_summary(db_session, owner, month=3, year=2026)
    assert march.expense_total_pln == 777
