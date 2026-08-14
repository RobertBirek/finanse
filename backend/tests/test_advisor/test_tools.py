import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.advisor.tools.registry import _execute_create_transaction, get_tool_by_name
from app.finance.schemas import AccountCreate, CategoryCreate
from app.finance.service import create_account, create_category, get_transaction


def account(name: str, currency: str = "PLN"):
    return SimpleNamespace(id=uuid.uuid4(), name=name, currency=currency)


def category(name: str = "Jedzenie", txn_type: str = "expense"):
    return SimpleNamespace(id=uuid.uuid4(), name=name, type=txn_type)


async def execute_transaction(monkeypatch, *, accounts, categories=None, **arguments):
    get_accounts = AsyncMock(return_value=accounts)
    get_categories = AsyncMock(return_value=categories or [category()])
    create_transaction = AsyncMock(
        return_value=SimpleNamespace(
            id=uuid.uuid4(),
            type=arguments.get("type", "expense"),
            description="[AI] Test",
            date="2026-08-12",
        )
    )
    monkeypatch.setattr("app.finance.service.get_accounts", get_accounts)
    monkeypatch.setattr("app.finance.service.get_categories", get_categories)
    monkeypatch.setattr("app.finance.service.create_transaction", create_transaction)

    result = await _execute_create_transaction(None, str(uuid.uuid4()), **arguments)
    return result, get_accounts, get_categories, create_transaction


@pytest.mark.asyncio
async def test_create_transaction_rejects_unmatched_account(monkeypatch):
    result, _, _, create_transaction = await execute_transaction(
        monkeypatch,
        accounts=[account("ING"), account("Gotowka")],
        amount=5000,
        account_name="Nieistniejace",
        description="Test",
    )

    assert result == {"error": "Account 'Nieistniejace' not found"}
    create_transaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_transaction_rejects_ambiguous_account_name(monkeypatch):
    result, _, _, create_transaction = await execute_transaction(
        monkeypatch,
        accounts=[account("ING"), account("ING")],
        amount=5000,
        account_name="ING",
        description="Test",
    )

    assert result == {"error": "Account 'ING' is ambiguous"}
    create_transaction.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("accounts", "expected_error"),
    [
        ([], "No accounts found; account_name is required"),
        ([account("ING")], "account_name is required"),
        (
            [account("ING"), account("Gotowka")],
            "account_name is required when multiple accounts exist",
        ),
    ],
)
async def test_create_transaction_does_not_guess_account_when_name_omitted(
    monkeypatch, accounts, expected_error
):
    result, _, _, create_transaction = await execute_transaction(
        monkeypatch,
        accounts=accounts,
        amount=5000,
        description="Test",
    )

    assert result == {"error": expected_error}
    create_transaction.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("amount", [0, -1, 1.5, True, "5000"])
async def test_create_transaction_rejects_invalid_amounts(monkeypatch, amount):
    result, get_accounts, _, create_transaction = await execute_transaction(
        monkeypatch,
        accounts=[account("ING")],
        amount=amount,
        account_name="ING",
        description="Test",
    )

    assert result == {"error": "Amount must be a positive integer"}
    get_accounts.assert_not_awaited()
    create_transaction.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("currency", ["EUR", "USD"])
async def test_create_transaction_rejects_non_pln_without_fx_rate(monkeypatch, currency):
    result, get_accounts, _, create_transaction = await execute_transaction(
        monkeypatch,
        accounts=[account("ING", currency)],
        amount=5000,
        currency=currency,
        account_name="ING",
        description="Test",
    )

    assert result == {"error": f"Advisor transactions in {currency} require a verified FX rate"}
    get_accounts.assert_not_awaited()
    create_transaction.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("account_currency", ["EUR", "USD"])
async def test_create_transaction_rejects_pln_for_non_pln_account(monkeypatch, account_currency):
    result, get_accounts, _, create_transaction = await execute_transaction(
        monkeypatch,
        accounts=[account("ING", account_currency)],
        amount=5000,
        currency="PLN",
        account_name="ING",
        description="Test",
    )

    assert result == {"error": f"Currency PLN does not match account currency {account_currency}"}
    get_accounts.assert_awaited_once()
    create_transaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_transaction_rejects_missing_category_for_requested_type(monkeypatch):
    result, _, _, create_transaction = await execute_transaction(
        monkeypatch,
        accounts=[account("ING")],
        categories=[category("Pensja", "income")],
        type="expense",
        amount=5000,
        account_name="ING",
        description="Zakupy",
    )

    assert result == {"error": "No expense category found"}
    create_transaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_transaction_creates_balanced_pln_postings(monkeypatch):
    selected_account = account("ING")
    result, _, _, create_transaction = await execute_transaction(
        monkeypatch,
        accounts=[selected_account],
        amount=5000,
        account_name="ing",
        description="Zakupy",
    )

    assert result["type"] == "expense"
    create_transaction.assert_awaited_once()
    transaction_data = create_transaction.await_args.args[2]
    assert len(transaction_data.postings) == 2
    assert [posting.source_currency for posting in transaction_data.postings] == ["PLN", "PLN"]
    assert [posting.base_amount_pln for posting in transaction_data.postings] == [5000, 5000]
    assert [posting.fx_rate for posting in transaction_data.postings] == [1.0, 1.0]
    assert [posting.direction for posting in transaction_data.postings] == ["credit", "debit"]
    assert [posting.account_id for posting in transaction_data.postings] == [
        selected_account.id,
        None,
    ]
    assert (
        sum(
            posting.base_amount_pln if posting.direction == "debit" else -posting.base_amount_pln
            for posting in transaction_data.postings
        )
        == 0
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_transaction_creates_category_only_pln_posting(db_session):
    user_id = uuid.uuid4()
    account_record = await create_account(
        db_session, user_id, AccountCreate(name="ING", type="checking")
    )
    category_record = await create_category(
        db_session, user_id, CategoryCreate(name="Jedzenie", type="expense")
    )

    result = await _execute_create_transaction(
        db_session,
        str(user_id),
        type="expense",
        amount=5000,
        currency="PLN",
        account_name="ING",
        category_name="Jedzenie",
        description="Zakupy",
    )

    assert "error" not in result
    transaction = await get_transaction(db_session, user_id, uuid.UUID(result["id"]))
    assert transaction is not None
    assert [(posting.account_id, posting.category_id) for posting in transaction.postings] == [
        (account_record.id, None),
        (None, category_record.id),
    ]


def test_create_transaction_tool_requires_account_and_positive_integer_amount():
    tool = get_tool_by_name("create_transaction")

    assert tool is not None
    assert tool.parameters["properties"]["amount"]["minimum"] == 1
