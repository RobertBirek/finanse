"""Compatibility and query-budget regressions for extracted finance reads."""

import uuid

import pytest
from sqlalchemy import event

from app.finance import queries, service
from app.finance.schemas import AccountCreate, CategoryCreate, PostingCreate, TransactionCreate

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_owned_account_detail_has_the_same_real_balance_as_list(db_session):
    user = uuid.uuid4()
    account = await service.create_account(
        db_session, user, AccountCreate(name="Main", type="checking")
    )
    category = await service.create_category(
        db_session, user, CategoryCreate(name="Expense", type="expense")
    )
    await service.create_transaction(
        db_session,
        user,
        TransactionCreate(
            description="Expense",
            type="expense",
            postings=[
                PostingCreate(
                    account_id=account.id,
                    source_amount=12345,
                    base_amount_pln=12345,
                    direction="debit",
                ),
                PostingCreate(
                    category_id=category.id,
                    source_amount=12345,
                    base_amount_pln=12345,
                    direction="credit",
                ),
            ],
        ),
    )
    # Check detail first: it used to fabricate zero unless list had populated _balance.
    detail = await service.get_account(db_session, user, account.id)
    assert detail.balance_pln == -12345
    listed = await service.get_accounts(db_session, user)
    assert listed[0].balance_pln == detail.balance_pln
    assert await service.get_account(db_session, uuid.uuid4(), account.id) is None
    assert service.get_transactions is queries.get_transactions
    assert service.search_transactions is queries.search_transactions


@pytest.mark.parametrize("number_of_accounts", [1, 12])
async def test_summary_has_constant_three_select_budget(db_session, number_of_accounts):
    user = uuid.uuid4()
    for n in range(number_of_accounts):
        await service.create_account(
            db_session, user, AccountCreate(name=f"Account {n}", type="checking")
        )
    await service.create_account(
        db_session, user, AccountCreate(name="Archived", type="checking", is_active=False)
    )
    await service.create_account(
        db_session, user, AccountCreate(name="Info", type="checking", is_budget_account=False)
    )
    await service.create_account(
        db_session, uuid.uuid4(), AccountCreate(name="Other owner", type="checking")
    )
    statements = []

    def count(_conn, _cursor, statement, _params, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    engine = db_session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", count)
    try:
        summary = await service.get_financial_summary(db_session, user, month=10, year=2026)
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert len(statements) == 3
    assert len(summary.accounts) == number_of_accounts
    assert all(account["balance_pln"] == 0 for account in summary.accounts)
