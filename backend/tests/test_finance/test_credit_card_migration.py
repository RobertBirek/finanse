"""The additive migration cannot discard saved card records on rollback."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_credit_cards import BASE, config, setup

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
FILE = (
    Path(__file__).parents[2]
    / "migrations/versions/00a9ccb532b9_credit_card_profiles_statements_and_.py"
)


def migration():
    spec = importlib.util.spec_from_file_location("card_migration", FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_downgrade_refuses_saved_card_without_losing_any_table(db_session):
    owner, card, _, _ = await setup(db_session)
    async with client_for(db_session, owner) as client:
        assert (await client.put(BASE.format(card.id), json=config())).status_code == 200

    def downgrade(connection):
        with Operations.context(MigrationContext.configure(connection)):
            migration().downgrade()

    async with db_session.begin_nested():
        with pytest.raises(RuntimeError, match="saved card"):
            await (await db_session.connection()).run_sync(downgrade)
    assert await db_session.scalar(text("SELECT count(*) FROM credit_cards")) == 1
    assert await db_session.scalar(text("SELECT to_regclass('card_installments') IS NOT NULL"))


async def test_empty_downgrade_reupgrade_preserves_old_accounts(db_session):
    _, account, _, _ = await setup(db_session)

    def roundtrip(connection):
        with Operations.context(MigrationContext.configure(connection)):
            migration().downgrade()
            migration().upgrade()

    await (await db_session.connection()).run_sync(roundtrip)
    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM accounts WHERE id=:id"), {"id": account.id}
        )
        == 1
    )
    assert await db_session.scalar(text("SELECT count(*) FROM credit_cards")) == 0
