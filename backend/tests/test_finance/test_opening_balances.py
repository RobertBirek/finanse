"""Opening balance changes money only once, never household income or expenses."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.finance import service
from app.finance.models import Account, FinancialTransaction, Posting
from app.finance.schemas import AccountCreate, AccountUpdate
from app.identity.models import User
from app.main import app as _app  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
DAY = date(2026, 11, 16)


async def owner_record(db):
    user = User(
        email=f"bo-{uuid.uuid4().hex}@example.test",
        display_name="Synthetic BO owner",
        password_hash="synthetic",
    )
    db.add(user)
    await db.flush()
    return user.id


async def opening_account(db, owner, amount=0, currency="PLN", **extra):
    return await service.create_account(
        db,
        owner,
        AccountCreate.model_validate(
            {
                "name": "Synthetic opening",
                "type": "checking",
                "currency": currency,
                "opening_balance": {
                    "amount_minor": amount,
                    "date": DAY.isoformat(),
                    **({"fx_rate": "4.123456"} if currency != "PLN" and amount else {}),
                },
                **extra,
            }
        ),
    )


async def test_opening_amount_is_ledger_only_and_reports_ignore_it(db_session):
    from app.finance.opening_balance_models import AccountOpeningBalance

    owner = await owner_record(db_session)
    for currency, amount, expected_base in [
        ("PLN", 125050, 125050),
        ("PLN", -125050, -125050),
        ("PLN", 0, 0),
        ("EUR", 125050, 515638),
        ("EUR", -125050, -515638),
        ("EUR", 0, 0),
        ("USD", 125050, 515638),
        ("USD", -125050, -515638),
        ("USD", 0, 0),
    ]:
        account = await opening_account(db_session, owner, amount, currency)
        assert account.balance_source == amount
        assert account.balance_pln == expected_base
        view = account.opening_balance
        assert view.amount_minor == amount and view.date == DAY
        assert view.can_edit and view.version == 1
        row = await db_session.scalar(
            select(AccountOpeningBalance).where(AccountOpeningBalance.account_id == account.id)
        )
        assert row is not None
        if not amount:
            assert row.transaction_id is None
            continue
        txn = await service.get_transaction(db_session, owner, row.transaction_id)
        assert txn.type == txn.source == "opening_balance"
        assert not txn.is_pending and len(txn.postings) == 2
        assert (
            sum(p.base_amount_pln * (1 if p.direction == "debit" else -1) for p in txn.postings)
            == 0
        )
        assert all(not p.is_budget_impact for p in txn.postings)
    summary = await service.get_financial_summary(db_session, owner, 11, 2026)
    assert summary.income_total_pln == summary.expense_total_pln == 0
    assert summary.balance_all_pln == 0
    assert await service.get_categories(db_session, owner) == []


async def test_opening_edit_replay_sign_change_and_zero(db_session):
    from app.finance.opening_balance_schemas import OpeningBalanceUpdate
    from app.finance.opening_balances import update_opening_balance

    owner = await owner_record(db_session)
    account = await opening_account(db_session, owner, 125050)
    data = OpeningBalanceUpdate(amount_minor=-25000, date=DAY, expected_version=1)
    result = await update_opening_balance(db_session, owner, account.id, data, "first")
    assert result.amount_minor == -25000 and result.version == 2
    assert (await update_opening_balance(db_session, owner, account.id, data, "first")) == result
    with pytest.raises(ValueError, match="klucz|key"):
        await update_opening_balance(
            db_session,
            owner,
            account.id,
            data.model_copy(update={"amount_minor": 40000}),
            "first",
        )
    assert (await service.get_account(db_session, owner, account.id)).balance_pln == -25000
    with pytest.raises(ValueError, match="wersj|version|zmieni"):
        await update_opening_balance(db_session, owner, account.id, data, "stale")
    zero = await update_opening_balance(
        db_session,
        owner,
        account.id,
        OpeningBalanceUpdate(amount_minor=0, date=DAY, expected_version=2),
        "zero",
    )
    assert zero.amount_minor == 0 and zero.version == 3
    assert await db_session.scalar(select(func.count()).select_from(Posting)) == 0
    assert await db_session.scalar(select(func.count()).select_from(FinancialTransaction)) == 0
    await service.update_account(db_session, owner, account.id, AccountUpdate(currency="EUR"))
    assert await service.delete_account(db_session, owner, account.id)


async def test_invalid_opening_is_atomic_and_currency_rules_apply(db_session):
    owner = await owner_record(db_session)
    for data in [
        {"currency": "EUR", "opening_balance": {"amount_minor": 100}},
        {"currency": "PLN", "opening_balance": {"amount_minor": 100, "fx_rate": "2"}},
        {
            "currency": "USD",
            "opening_balance": {
                "amount_minor": 9007199254740991,
                "fx_rate": "4.123456",
            },
        },
    ]:
        with pytest.raises(ValueError):
            await service.create_account(
                db_session,
                owner,
                AccountCreate.model_validate({"name": "Invalid BO", "type": "cash", **data}),
            )
        assert await db_session.scalar(select(func.count()).select_from(Account)) == 0
    account = await opening_account(db_session, owner, -100)
    with pytest.raises(ValueError, match="walut|currency"):
        await service.update_account(db_session, owner, account.id, AccountUpdate(currency="EUR"))
    with pytest.raises(ValidationError):
        AccountUpdate.model_validate({"opening_balance": {"amount_minor": 100}})


@pytest.mark.parametrize(
    "values",
    [
        {"amount_minor": True},
        {"amount_minor": 1.5},
        {"amount_minor": 9007199254740992},
        {"amount_minor": -9007199254740992},
        {"fx_rate": "NaN"},
        {"fx_rate": "Infinity"},
        {"fx_rate": "1.1234567"},
        {"fx_rate": "-1"},
    ],
)
async def test_opening_input_rejects_lossy_or_nonfinite_values(values):
    from app.finance.opening_balance_schemas import OpeningBalanceInput

    with pytest.raises(ValidationError):
        OpeningBalanceInput.model_validate(values)


async def test_foreign_half_even_and_zero_needs_no_quote(db_session):
    from app.finance.opening_balance_schemas import OpeningBalanceInput

    owner = await owner_record(db_session)
    for amount, expected in [(1, 2), (-1, -2), (3, 8), (-3, -8)]:
        account = await service.create_account(
            db_session,
            owner,
            AccountCreate(
                name="Half even",
                type="cash",
                currency="USD",
                opening_balance=OpeningBalanceInput(
                    amount_minor=amount, date=DAY, fx_rate=Decimal("2.5")
                ),
            ),
        )
        assert account.balance_pln == expected


async def test_negative_card_opening_updates_debt_and_forecast_without_expense(db_session):
    from app.finance.credit_cards import list_summaries

    owner = await owner_record(db_session)
    card = await opening_account(
        db_session,
        owner,
        -25000,
        type="credit_card",
        credit_card={
            "limit_pln": 100000,
            "apr": "14.5",
            "cycle_close_day": 17,
            "due_day": 12,
            "grace_days": 57,
            "expected_version": 0,
        },
    )
    summary = (await list_summaries(db_session, owner))[0]
    assert summary.account_id == card.id
    assert summary.debt_pln == 25000 and summary.available_pln == 75000
    forecast = await service.get_cashflow_forecast(db_session, owner)
    assert forecast.opening_balance_pln == -25000
