"""A manual refund restores the account and reduces expense, never income."""

import uuid
from datetime import date

import pytest
from sqlalchemy import func, select

from app.audit.models import AuditEvent
from app.finance.models import FinancialTransaction, Posting
from app.finance.rule_event_models import TransactionRuleEvent
from app.finance.schemas import AccountCreate, CategoryBudgetCreate, CategoryCreate
from app.finance.service import (
    create_account,
    create_budget,
    create_category,
    delete_transaction,
    get_account,
    get_budget_status,
    get_category_summary,
    get_financial_summary,
)
from app.finance.suggestion_models import CategorizationSuggestionJob
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_bill_payments import create_owner
from tests.test_finance.test_budgets import create_expense_transaction

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
URL = "/api/finance/transactions/expense-refund"


async def setup(db):
    owner = await create_owner(db)
    account = await create_account(
        db, owner, AccountCreate(name="Bank", type="checking", currency="PLN")
    )
    category = await create_category(db, owner, CategoryCreate(name="Naprawy", type="expense"))
    return owner, account, category


def payload(account, category, **updates):
    return {
        "account_id": str(account.id),
        "category_id": str(category.id),
        "amount_minor": 15000,
        "transaction_date": "2026-11-12",
        "description": "Zwrot części towaru",
        **updates,
    }


async def test_partial_refund_reduces_expense_budget_and_restores_balance(db_session):
    db = db_session
    owner, account, category = await setup(db)
    await create_budget(db, owner, CategoryBudgetCreate(category_id=category.id, amount_pln=60000))
    await create_expense_transaction(
        db, owner, account.id, category.id, amount=50000, txn_date=date(2026, 11, 1)
    )
    async with client_for(db, owner) as client:
        response = await client.post(URL, json=payload(account, category))
    assert response.status_code == 201, response.text
    txn = response.json()
    assert (txn["type"], txn["source"], txn["transaction_date"]) == (
        "expense",
        "manual",
        "2026-11-12",
    )
    assert len(txn["postings"]) == 2
    assert [
        (p["account_id"], p["category_id"], p["direction"], p["base_amount_pln"])
        for p in sorted(txn["postings"], key=lambda p: p["account_id"] is None)
    ] == [(str(account.id), None, "credit", 15000), (None, str(category.id), "debit", 15000)]
    assert (
        sum(
            p["base_amount_pln"] * (1 if p["direction"] == "debit" else -1) for p in txn["postings"]
        )
        == 0
    )
    assert (await get_account(db, owner, account.id)).balance_pln == -35000
    summary = await get_financial_summary(db, owner, 11, 2026)
    assert (summary.income_total_pln, summary.expense_total_pln, summary.net_total_pln) == (
        0,
        35000,
        -35000,
    )
    cats = await get_category_summary(db, owner, 11, 2026)
    assert next(c.total_pln for c in cats.categories if c.category_id == category.id) == 35000
    budget = await get_budget_status(db, owner, 11, 2026)
    item = next(i for i in budget.items if i.category_id == category.id)
    assert (item.spent_pln, item.remaining_pln) == (35000, 25000)
    event = await db.scalar(select(AuditEvent).where(AuditEvent.entity_id == txn["id"]))
    assert event.action == "create_expense_refund" and event.user_id == owner
    await delete_transaction(db, owner, uuid.UUID(txn["id"]))
    assert (await get_account(db, owner, account.id)).balance_pln == -50000


async def test_standalone_refund_uses_its_own_month_and_nonbudget_flag(db_session):
    db = db_session
    owner, account, category = await setup(db)
    account.is_budget_account = False
    await db.flush()
    async with client_for(db, owner) as client:
        response = await client.post(URL, json=payload(account, category))
    assert response.status_code == 201, response.text
    assert all(p["is_budget_impact"] is False for p in response.json()["postings"])
    assert await db.scalar(select(func.count()).select_from(TransactionRuleEvent)) == 0
    assert await db.scalar(select(func.count()).select_from(CategorizationSuggestionJob)) == 0
    assert (await get_account(db, owner, account.id)).balance_pln == 15000
    summary = await get_financial_summary(db, owner, 11, 2026)
    assert (summary.income_total_pln, summary.expense_total_pln) == (0, 0)


async def test_refund_in_new_month_does_not_rewrite_original_purchase(db_session):
    db = db_session
    owner, account, category = await setup(db)
    await create_expense_transaction(
        db, owner, account.id, category.id, amount=50000, txn_date=date(2026, 10, 1)
    )
    async with client_for(db, owner) as client:
        response = await client.post(URL, json=payload(account, category, amount_minor=60000))
    assert response.status_code == 201, response.text
    assert (await get_financial_summary(db, owner, 10, 2026)).expense_total_pln == 50000
    current = await get_financial_summary(db, owner, 11, 2026)
    assert (current.income_total_pln, current.expense_total_pln) == (0, -60000)


@pytest.mark.parametrize(
    "patch",
    [
        {"amount_minor": 0},
        {"amount_minor": -1},
        {"amount_minor": True},
        {"amount_minor": "15000"},
        {"amount_minor": 1.5},
        {"amount_minor": 9007199254740992},
        {"description": "  "},
        {"transaction_date": "bad"},
        {"source": "bank_import"},
        {"postings": []},
        {"is_pending": True},
        {"type": "income"},
        {"allow_manual_refund": True},
    ],
)
async def test_strict_refund_command_rejects_client_controlled_ledger_fields(db_session, patch):
    owner, account, category = await setup(db_session)
    async with client_for(db_session, owner) as client:
        result = await client.post(URL, json=payload(account, category, **patch))
    assert result.status_code == 422, result.text
    assert await db_session.scalar(select(func.count()).select_from(FinancialTransaction)) == 0


@pytest.mark.parametrize(
    "invalid",
    [
        "other_account",
        "other_category",
        "income",
        "inactive_account",
        "inactive_category",
        "foreign_currency",
    ],
)
async def test_refund_owner_active_type_and_currency_guards(db_session, invalid):
    db = db_session
    owner, account, category = await setup(db)
    if invalid == "other_account":
        account.user_id = uuid.uuid4()
    elif invalid == "other_category":
        category.user_id = uuid.uuid4()
    elif invalid == "income":
        category.type = "income"
    elif invalid == "inactive_account":
        account.is_active = False
    elif invalid == "inactive_category":
        category.is_active = False
    else:
        account.currency = "EUR"
    await db.flush()
    async with client_for(db, owner) as client:
        result = await client.post(URL, json=payload(account, category))
    assert result.status_code == 422, result.text
    assert await db.scalar(select(func.count()).select_from(Posting)) == 0


async def test_public_transaction_route_cannot_claim_refund_permission(db_session):
    owner, account, category = await setup(db_session)
    async with client_for(db_session, owner) as client:
        result = await client.post(
            "/api/finance/transactions",
            json={
                "type": "expense",
                "source": "manual",
                "description": "Fake refund",
                "postings": [
                    {
                        "account_id": str(account.id),
                        "source_amount": 100,
                        "base_amount_pln": 100,
                        "direction": "credit",
                    },
                    {
                        "category_id": str(category.id),
                        "source_amount": 100,
                        "base_amount_pln": 100,
                        "direction": "debit",
                    },
                ],
            },
        )
    assert result.status_code == 422


async def test_refund_endpoint_requires_authenticated_owner(async_client):
    result = await async_client.post(
        URL,
        json={
            "account_id": str(uuid.uuid4()),
            "category_id": str(uuid.uuid4()),
            "amount_minor": 100,
            "transaction_date": "2026-11-12",
            "description": "Zwrot",
        },
    )
    assert result.status_code == 401
