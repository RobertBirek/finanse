"""Tests for currency exchange (przewalutowanie) PLN-EUR-USD."""

import uuid

import pytest

from app.finance.nbp_rates import NbpRate, NbpRateProvider
from app.finance.schemas import AccountCreate, ExchangeCreate
from app.finance.service import create_account, create_exchange_transaction


async def _make_account(db_session, user_id, *, name, currency, is_active=True):
    return await create_account(
        db_session,
        user_id,
        AccountCreate(name=name, type="checking", currency=currency, is_active=is_active),
    )


def _posting_by_direction(txn, direction):
    return next(p for p in txn.postings if p.direction == direction)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_exchange_pln_to_eur_manual_rate(db_session):
    user_id = uuid.uuid4()
    pln = await _make_account(db_session, user_id, name="PLN", currency="PLN")
    eur = await _make_account(db_session, user_id, name="EUR", currency="EUR")

    txn = await create_exchange_transaction(
        db_session,
        user_id,
        ExchangeCreate(
            from_account_id=pln.id,
            to_account_id=eur.id,
            from_amount=430,
            fx_rate=4.3,
            description="Przewalutowanie PLN->EUR",
        ),
    )

    assert txn.type == "exchange"
    assert len(txn.postings) == 2

    debit = _posting_by_direction(txn, "debit")
    credit = _posting_by_direction(txn, "credit")

    assert debit.account_id == pln.id
    assert debit.source_currency == "PLN"
    assert debit.source_amount == 430
    assert debit.base_amount_pln == 430
    assert float(debit.fx_rate) == 1.0

    assert credit.account_id == eur.id
    assert credit.source_currency == "EUR"
    assert credit.source_amount == 100
    assert credit.base_amount_pln == 430
    assert float(credit.fx_rate) == 4.3
    assert credit.fx_rate_source == "manual"

    assert debit.base_amount_pln == credit.base_amount_pln


@pytest.mark.integration
@pytest.mark.asyncio
async def test_exchange_eur_to_pln_manual_rate(db_session):
    user_id = uuid.uuid4()
    eur = await _make_account(db_session, user_id, name="EUR", currency="EUR")
    pln = await _make_account(db_session, user_id, name="PLN", currency="PLN")

    txn = await create_exchange_transaction(
        db_session,
        user_id,
        ExchangeCreate(
            from_account_id=eur.id,
            to_account_id=pln.id,
            from_amount=100,
            fx_rate=4.3,
            description="Przewalutowanie EUR->PLN",
        ),
    )

    debit = _posting_by_direction(txn, "debit")
    credit = _posting_by_direction(txn, "credit")

    assert debit.account_id == eur.id
    assert debit.source_currency == "EUR"
    assert debit.source_amount == 100
    assert debit.base_amount_pln == 430
    assert float(debit.fx_rate) == 4.3

    assert credit.account_id == pln.id
    assert credit.source_currency == "PLN"
    assert credit.source_amount == 430
    assert credit.base_amount_pln == 430
    assert float(credit.fx_rate) == 1.0

    assert debit.base_amount_pln == credit.base_amount_pln


@pytest.mark.integration
@pytest.mark.asyncio
async def test_exchange_uses_nbp_rate_source(db_session, monkeypatch):
    user_id = uuid.uuid4()
    pln = await _make_account(db_session, user_id, name="PLN", currency="PLN")
    eur = await _make_account(db_session, user_id, name="EUR", currency="EUR")

    async def fake_get_rate(self, currency, rate_date):
        return NbpRate(rate=4.2, effective_date=rate_date, source="nbp")

    monkeypatch.setattr(NbpRateProvider, "get_rate", fake_get_rate)

    txn = await create_exchange_transaction(
        db_session,
        user_id,
        ExchangeCreate(
            from_account_id=pln.id,
            to_account_id=eur.id,
            from_amount=420,
            description="Przewalutowanie NBP",
        ),
    )

    credit = _posting_by_direction(txn, "credit")
    assert credit.fx_rate_source == "nbp"
    assert float(credit.fx_rate) == 4.2
    assert credit.source_amount == 100
    assert credit.base_amount_pln == 420


@pytest.mark.integration
@pytest.mark.asyncio
async def test_exchange_both_foreign_raises(db_session):
    user_id = uuid.uuid4()
    eur = await _make_account(db_session, user_id, name="EUR", currency="EUR")
    usd = await _make_account(db_session, user_id, name="USD", currency="USD")

    with pytest.raises(ValueError, match="Cross-currency exchange is not supported"):
        await create_exchange_transaction(
            db_session,
            user_id,
            ExchangeCreate(
                from_account_id=eur.id,
                to_account_id=usd.id,
                from_amount=100,
                fx_rate=1.0,
                description="EUR->USD",
            ),
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_exchange_both_pln_raises(db_session):
    user_id = uuid.uuid4()
    a = await _make_account(db_session, user_id, name="A", currency="PLN")
    b = await _make_account(db_session, user_id, name="B", currency="PLN")

    with pytest.raises(ValueError, match="different currencies"):
        await create_exchange_transaction(
            db_session,
            user_id,
            ExchangeCreate(
                from_account_id=a.id, to_account_id=b.id, from_amount=100, description="PLN->PLN"
            ),
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_exchange_foreign_account_raises(db_session):
    user_id = uuid.uuid4()
    other_user = uuid.uuid4()
    pln = await _make_account(db_session, user_id, name="PLN", currency="PLN")
    foreign = await _make_account(db_session, other_user, name="Foreign EUR", currency="EUR")

    with pytest.raises(ValueError, match="not found"):
        await create_exchange_transaction(
            db_session,
            user_id,
            ExchangeCreate(
                from_account_id=pln.id,
                to_account_id=foreign.id,
                from_amount=100,
                description="Cudze konto",
            ),
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_exchange_inactive_account_raises(db_session):
    user_id = uuid.uuid4()
    pln = await _make_account(db_session, user_id, name="PLN", currency="PLN")
    eur = await _make_account(db_session, user_id, name="EUR", currency="EUR", is_active=False)

    with pytest.raises(ValueError, match="not active"):
        await create_exchange_transaction(
            db_session,
            user_id,
            ExchangeCreate(
                from_account_id=pln.id,
                to_account_id=eur.id,
                from_amount=100,
                description="Nieaktywne konto",
            ),
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_exchange_no_rate_raises(db_session, monkeypatch):
    user_id = uuid.uuid4()
    pln = await _make_account(db_session, user_id, name="PLN", currency="PLN")
    eur = await _make_account(db_session, user_id, name="EUR", currency="EUR")

    async def fake_get_rate(self, currency, rate_date):
        return None

    monkeypatch.setattr(NbpRateProvider, "get_rate", fake_get_rate)

    with pytest.raises(ValueError, match="No FX rate"):
        await create_exchange_transaction(
            db_session,
            user_id,
            ExchangeCreate(
                from_account_id=pln.id,
                to_account_id=eur.id,
                from_amount=100,
                description="Brak kursu",
            ),
        )
