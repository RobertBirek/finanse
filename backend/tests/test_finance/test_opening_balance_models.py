"""BO identity must not permit duplicate or cross-owner ledger references."""

import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.finance.models import Account, Category, FinancialTransaction
from app.main import app as _app  # noqa: F401 - register models

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_opening_balance_owner_and_uniqueness(db_session):
    from app.finance.opening_balance_models import AccountOpeningBalance

    owner, other = uuid.uuid4(), uuid.uuid4()
    account = Account(user_id=owner, name="Synthetic", type="checking")
    second = Account(user_id=owner, name="Other account", type="cash")
    foreign = Account(user_id=other, name="Foreign", type="cash")
    txn = FinancialTransaction(user_id=other, description="Foreign", type="transfer")
    db_session.add_all([account, second, foreign, txn])
    await db_session.flush()
    ids = account.id, second.id, foreign.id, txn.id
    record = AccountOpeningBalance(
        user_id=owner, account_id=ids[0], opening_date=date(2026, 11, 16)
    )
    db_session.add(record)
    await db_session.flush()
    for values in [
        {"user_id": owner, "account_id": ids[0]},
        {"user_id": owner, "account_id": ids[2]},
        {"user_id": owner, "account_id": ids[1], "transaction_id": ids[3]},
        {"user_id": owner, "account_id": ids[1], "version": 0},
    ]:
        with pytest.raises(IntegrityError):
            async with db_session.begin_nested():
                db_session.add(AccountOpeningBalance(opening_date=date(2026, 11, 16), **values))
                await db_session.flush()
    stored = await db_session.scalar(
        select(AccountOpeningBalance).where(AccountOpeningBalance.account_id == ids[0])
    )
    assert stored is not None
    assert stored.transaction_id is None
    assert stored.version == 1


async def test_only_one_technical_opening_category_per_owner(db_session):
    owner = uuid.uuid4()
    db_session.add(
        Category(user_id=owner, name="Technical", type="transfer", source="opening_balance")
    )
    await db_session.flush()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                Category(user_id=owner, name="Duplicate", type="transfer", source="opening_balance")
            )
            await db_session.flush()
