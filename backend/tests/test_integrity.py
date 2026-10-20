"""Regression coverage for audit findings against an isolated PostgreSQL database."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.finance import service as finance
from app.finance.models import FinancialTransaction
from app.finance.schemas import (
    AccountCreate,
    CategoryCreate,
    CategoryUpdate,
    ExchangeCreate,
    PostingCreate,
    TransactionCreate,
    TransactionUpdate,
)
from app.inbox.models import InboxItem
from app.inbox.schemas import InboxItemCreate, ProcessInboxItem
from app.inbox.service import create_inbox_item, process_inbox_item
from app.work import service as work
from app.work.schemas import ProjectCreate, TaskCreate, TaskUpdate, TimeBlockCreate, TimeBlockUpdate

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def expense_data(db, user_id, currency="PLN"):
    account = await finance.create_account(
        db, user_id, AccountCreate(name="Account", type="checking", currency=currency)
    )
    category = await finance.create_category(
        db, user_id, CategoryCreate(name="Expenses", type="expense")
    )
    rate = 1 if currency == "PLN" else 4.3
    base = 100 if currency == "PLN" else 430
    return TransactionCreate(
        description="Regression",
        transaction_date=date(2026, 1, 10),
        type="expense",
        postings=[
            PostingCreate(
                account_id=account.id,
                source_amount=100,
                source_currency=currency,
                base_amount_pln=base,
                fx_rate=rate,
                direction="debit",
            ),
            PostingCreate(
                category_id=category.id,
                source_amount=100,
                source_currency=currency,
                base_amount_pln=base,
                fx_rate=rate,
                direction="credit",
            ),
        ],
    )


@pytest.mark.parametrize("case", ["base", "pln-rate", "direction", "category-type", "combined"])
async def test_rejects_balanced_but_invalid_expense(db_session, case):
    user = uuid.uuid4()
    data = await expense_data(db_session, user)
    if case == "base":
        for posting in data.postings:
            posting.base_amount_pln = 10000
    elif case == "pln-rate":
        for posting in data.postings:
            posting.fx_rate = 2
    elif case == "direction":
        for posting in data.postings:
            posting.direction = "credit" if posting.direction == "debit" else "debit"
    elif case == "category-type":
        category = await finance.create_category(
            db_session, user, CategoryCreate(name="Income", type="income")
        )
        data.postings[1].category_id = category.id
    else:
        data.postings[1].account_id = data.postings[0].account_id
    with pytest.raises(ValueError):
        await finance.create_transaction(db_session, user, data)
    count = await db_session.scalar(select(func.count()).select_from(FinancialTransaction))
    assert count == 0


async def test_rejects_inconsistent_foreign_amounts(db_session):
    user = uuid.uuid4()
    data = await expense_data(db_session, user, "EUR")
    for posting in data.postings:
        posting.base_amount_pln = 431
    with pytest.raises(ValueError, match="Base amount"):
        await finance.create_transaction(db_session, user, data)


@pytest.mark.parametrize("amount, expected", [(1, 0), (3, 2), (5, 2), (7, 4)])
async def test_decimal_half_even_rounding(db_session, amount, expected):
    user = uuid.uuid4()
    data = await expense_data(db_session, user, "EUR")
    for posting in data.postings:
        posting.source_amount = amount
        posting.fx_rate = 0.5
        posting.base_amount_pln = expected
    if expected == 0:
        with pytest.raises(ValueError, match="positive"):
            await finance.create_transaction(db_session, user, data)
    else:
        transaction = await finance.create_transaction(db_session, user, data)
        assert transaction.postings[0].base_amount_pln == expected


async def test_exchange_preserves_minor_unit_rounding(db_session):
    user = uuid.uuid4()
    source = await finance.create_account(
        db_session, user, AccountCreate(name="PLN", type="checking")
    )
    target = await finance.create_account(
        db_session, user, AccountCreate(name="EUR", type="checking", currency="EUR")
    )
    transaction = await finance.create_exchange_transaction(
        db_session,
        user,
        ExchangeCreate(
            from_account_id=source.id,
            to_account_id=target.id,
            from_amount=100,
            fx_rate=4.3,
            description="Rounded receipt",
        ),
    )
    assert [p.source_amount for p in transaction.postings] == [100, 23]
    assert [p.base_amount_pln for p in transaction.postings] == [100, 100]


async def test_transaction_date_survives_commit_and_changes_reporting_month(db_session):
    user = uuid.uuid4()
    transaction = await finance.create_transaction(
        db_session, user, await expense_data(db_session, user)
    )
    transaction_id = transaction.id
    await finance.update_transaction(
        db_session,
        user,
        transaction_id,
        TransactionUpdate(
            transaction_date=date(2026, 2, 10),
            description="Moved",
        ),
    )
    await db_session.commit()
    db_session.expunge_all()
    persisted = await finance.get_transaction(db_session, user, transaction_id)
    assert persisted.date == date(2026, 2, 10)
    assert persisted.description == "Moved"
    assert (await finance.get_financial_summary(db_session, user, 1, 2026)).expense_total_pln == 0
    assert (await finance.get_financial_summary(db_session, user, 2, 2026)).expense_total_pln == 100


@pytest.mark.parametrize("on_update", [False, True])
async def test_transaction_rejects_foreign_project(db_session, on_update):
    user = uuid.uuid4()
    foreign = await work.create_project(db_session, uuid.uuid4(), ProjectCreate(name="Private"))
    data = await expense_data(db_session, user)
    if on_update:
        transaction = await finance.create_transaction(db_session, user, data)
        with pytest.raises(ValueError, match="Project not found"):
            await finance.update_transaction(
                db_session, user, transaction.id, TransactionUpdate(project_id=foreign.id)
            )
        assert transaction.project_id is None
    else:
        data.project_id = foreign.id
        with pytest.raises(ValueError, match="Project not found"):
            await finance.create_transaction(db_session, user, data)


async def test_categories_reject_foreign_parent_and_cycles(db_session):
    user = uuid.uuid4()
    foreign = await finance.create_category(
        db_session, uuid.uuid4(), CategoryCreate(name="Private", type="expense")
    )
    with pytest.raises(ValueError, match="Parent category not found"):
        await finance.create_category(
            db_session,
            user,
            CategoryCreate(
                name="Invalid",
                type="expense",
                parent_id=foreign.id,
            ),
        )
    root = await finance.create_category(
        db_session, user, CategoryCreate(name="Root", type="expense")
    )
    child = await finance.create_category(
        db_session,
        user,
        CategoryCreate(
            name="Child",
            type="expense",
            parent_id=root.id,
        ),
    )
    for parent in [root.id, child.id]:
        with pytest.raises(ValueError, match="cycles"):
            await finance.update_category(
                db_session, user, root.id, CategoryUpdate(parent_id=parent)
            )
    assert root.parent_id is None
    with pytest.raises(ValueError, match="type must match"):
        await finance.create_category(
            db_session,
            user,
            CategoryCreate(
                name="Invalid",
                type="income",
                parent_id=root.id,
            ),
        )


async def test_work_links_reject_other_users_objects_on_create_and_update(db_session):
    user = uuid.uuid4()
    foreign = await work.create_project(db_session, uuid.uuid4(), ProjectCreate(name="Private"))
    foreign_task = await work.create_task(db_session, foreign.user_id, TaskCreate(title="Private"))
    with pytest.raises(ValueError, match="Project not found"):
        await work.create_task(db_session, user, TaskCreate(title="Invalid", project_id=foreign.id))
    task = await work.create_task(db_session, user, TaskCreate(title="Owned"))
    with pytest.raises(ValueError, match="Project not found"):
        await work.update_task(db_session, user, task.id, TaskUpdate(project_id=foreign.id))
    now = datetime.now(UTC)
    data = TimeBlockCreate(title="Block", start_time=now, end_time=now + timedelta(hours=1))
    with pytest.raises(ValueError, match="Task not found"):
        await work.create_time_block(
            db_session, user, data.model_copy(update={"task_id": foreign_task.id})
        )
    with pytest.raises(ValueError, match="Project not found"):
        await work.create_time_block(
            db_session, user, data.model_copy(update={"project_id": foreign.id})
        )
    block = await work.create_time_block(db_session, user, data)
    with pytest.raises(ValueError, match="Task not found"):
        await work.update_time_block(
            db_session, user, block.id, TimeBlockUpdate(task_id=foreign_task.id)
        )
    assert block.task_id is None
    assert task.project_id is None


@pytest.mark.parametrize("target", ["project", "transaction", "document", "decision"])
async def test_inbox_rejects_unimplemented_conversion_without_losing_item(db_session, target):
    user = uuid.uuid4()
    item = await create_inbox_item(db_session, user, InboxItemCreate(content="Keep me"))
    with pytest.raises(ValueError, match="not available"):
        await process_inbox_item(db_session, user, item.id, ProcessInboxItem(target_type=target))
    await db_session.refresh(item)
    assert not item.is_processed
    assert item.target_id is None


async def test_inbox_task_is_created_once(db_session):
    user = uuid.uuid4()
    item = await create_inbox_item(db_session, user, InboxItemCreate(content="Do this"))
    processed, task = await process_inbox_item(
        db_session, user, item.id, ProcessInboxItem(target_type="task")
    )
    assert task.title == "Do this"
    assert processed.target_id == task.id
    with pytest.raises(ValueError, match="already processed"):
        await process_inbox_item(db_session, user, item.id, ProcessInboxItem(target_type="task"))
    assert (await db_session.get(InboxItem, item.id)).is_processed


async def test_transaction_patch_api_updates_date_and_rejects_foreign_project(
    db_session, async_client
):
    from types import SimpleNamespace

    from app.identity.router import get_current_user
    from app.main import app

    user = uuid.uuid4()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user)
    transaction = await finance.create_transaction(
        db_session, user, await expense_data(db_session, user)
    )
    response = await async_client.patch(
        f"/api/finance/transactions/{transaction.id}", json={"transaction_date": "2026-02-10"}
    )
    assert response.status_code == 200
    assert response.json()["transaction_date"] == "2026-02-10"
    foreign = await work.create_project(db_session, uuid.uuid4(), ProjectCreate(name="Private"))
    invalid = await async_client.patch(
        f"/api/finance/transactions/{transaction.id}", json={"project_id": str(foreign.id)}
    )
    assert invalid.status_code == 422
    assert transaction.project_id is None


@pytest.mark.parametrize(
    "kind,category_type,expected_income,expected_expense",
    [
        ("income", "expense", 0, -100),
        ("expense", "income", -100, 0),
    ],
)
async def test_actual_reversals_preserve_category_semantics_and_signed_reports(
    db_session, kind, category_type, expected_income, expected_expense
):
    from app.finance.schemas import CategoryBudgetCreate

    user = uuid.uuid4()
    account = await finance.create_account(
        db_session, user, AccountCreate(name="Source", type="checking")
    )
    category = await finance.create_category(
        db_session, user, CategoryCreate(name="Original category", type=category_type)
    )
    direction = "credit" if kind == "income" else "debit"
    data = TransactionCreate(
        description="Imported reversal",
        type=kind,
        source="actual",
        transaction_date=date(2026, 1, 10),
        postings=[
            PostingCreate(
                account_id=account.id, source_amount=100, base_amount_pln=100, direction=direction
            ),
            PostingCreate(
                category_id=category.id,
                source_amount=100,
                base_amount_pln=100,
                direction="debit" if direction == "credit" else "credit",
            ),
        ],
    )
    # Spoofing source=actual through the normal service path does not bypass checks.
    with pytest.raises(ValueError, match="Category type"):
        await finance.create_transaction(db_session, user, data)
    transaction = await finance.create_transaction(
        db_session, user, data, allow_category_reversal=True
    )
    summary = await finance.get_financial_summary(db_session, user, 1, 2026)
    assert summary.income_total_pln == expected_income
    assert summary.expense_total_pln == expected_expense
    assert transaction.type == kind
    assert transaction.postings[1].category_id == category.id
    if category_type == "expense":
        await finance.create_budget(
            db_session, user, CategoryBudgetCreate(category_id=category.id, amount_pln=500)
        )
        status = await finance.get_budget_status(db_session, user, 1, 2026)
        assert status.items[0].spent_pln == -100
        assert status.items[0].remaining_pln == 600
        categories = await finance.get_category_summary(db_session, user, 1, 2026)
        assert categories.categories[0].total_pln == -100
    # Reversal support still enforces account ownership.
    with pytest.raises(ValueError, match="Account not found"):
        await finance.create_transaction(
            db_session, uuid.uuid4(), data, allow_category_reversal=True
        )
