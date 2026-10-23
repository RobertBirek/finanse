"""Closed accounts retain history without being reopened or bypassing API policy."""

import json
import sqlite3
import uuid
import zipfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.finance.actual_parser import ActualParser
from app.finance.models import Account, ActualImportMapping, FinancialTransaction
from app.finance.reconciliation import ReconciliationError
from app.finance.schemas import AccountCreate, PostingCreate, TransactionCreate
from app.finance.service import create_account, create_transaction
from scripts import migrate_actual as importer


def make_closed_export(tmp_path: Path, currency: str = "PLN", use_view: bool = False) -> Path:
    path = tmp_path / "db.sqlite"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
            CREATE TABLE categories (id TEXT, name TEXT, is_income INTEGER, cat_group TEXT, tombstone INTEGER);
            CREATE TABLE category_groups (id TEXT, name TEXT, tombstone INTEGER);
            CREATE TABLE payees (id TEXT, name TEXT);
            CREATE TABLE payee_mapping (id TEXT, payeeId TEXT);
            CREATE TABLE transactions (id TEXT, acct TEXT, category TEXT, amount INTEGER,
                description TEXT, payee TEXT, notes TEXT, date INTEGER, tombstone INTEGER,
                isParent INTEGER, isChild INTEGER, parent_id TEXT, transferred_id TEXT);
            INSERT INTO category_groups VALUES ('g', 'Group', 0);
            INSERT INTO categories VALUES ('c', 'Category', 0, 'g', 0);
            INSERT INTO transactions VALUES ('t1','open',NULL,-500,NULL,NULL,NULL,20261001,0,0,0,NULL,'t2');
            INSERT INTO transactions VALUES ('t2','closed',NULL,500,NULL,NULL,NULL,20261001,0,0,0,NULL,'t1');
            INSERT INTO transactions VALUES ('t3','closed',NULL,-500,NULL,NULL,NULL,20261002,0,0,0,NULL,'t4');
            INSERT INTO transactions VALUES ('t4','open',NULL,500,NULL,NULL,NULL,20261002,0,0,0,NULL,'t3');
            INSERT INTO transactions VALUES ('expense','closed','c',-123,NULL,NULL,'Expense',20261003,0,0,0,NULL,NULL);
            INSERT INTO transactions VALUES ('split','closed',NULL,-100,NULL,NULL,NULL,20261004,0,1,0,NULL,NULL);
            INSERT INTO transactions VALUES ('child1','closed','c',-40,NULL,NULL,NULL,20261004,0,0,1,'split',NULL);
            INSERT INTO transactions VALUES ('child2','closed','c',-60,NULL,NULL,NULL,20261004,0,0,1,'split',NULL);
        """)
        conn.executemany(
            "INSERT INTO accounts VALUES (?,?,?,?,?)",
            [
                ("open", f"Open {currency}", 0, 0, 0),
                ("closed", f"Closed {currency}", 1, 1, 0),
                ("empty", "Empty closed", 0, 1, 0),
                ("deleted", "Deleted", 0, 1, 1),
            ],
        )
        if use_view:
            conn.execute("""CREATE VIEW v_transactions AS SELECT *, acct AS account,
                transferred_id AS transfer_id, isParent AS is_parent, isChild AS is_child FROM transactions""")
    return path


@pytest.mark.parametrize("use_view", [False, True])
def test_parser_keeps_closed_accounts_and_native_currency(tmp_path: Path, use_view: bool) -> None:
    with ActualParser(make_closed_export(tmp_path, "USD", use_view)) as parser:
        accounts = {a["actual_id"]: a for a in parser.get_accounts()}
        assert set(accounts) == {"open", "closed", "empty"}
        assert accounts["open"]["is_active"] is True
        assert accounts["closed"]["is_active"] is False
        assert accounts["empty"]["is_active"] is False
        assert accounts["closed"]["is_budget_account"] is False
        operations = parser.get_transactions() + parser.get_transfers() + parser.get_splits()
        assert len(operations) == 4
        assert all(p["source_currency"] == "USD" for t in operations for p in t["postings"])
        assert all("?" not in t["description"] for t in parser.get_transfers())
        balances = parser.get_account_balances()
        assert set(balances) == set(accounts)
        assert balances["closed"].amount == -223  # split children are not counted twice
        assert balances["closed"].currency == "USD"
        assert balances["empty"].amount == 0


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source,allow_history,accepted",
    [
        ("manual", False, False),
        ("actual", False, False),
        ("manual", True, False),
        ("actual", True, True),
    ],
)
async def test_inactive_account_history_requires_trusted_opt_in(
    db_session: AsyncSession, source: str, allow_history: bool, accepted: bool
) -> None:
    user = uuid.uuid4()
    active = await create_account(db_session, user, AccountCreate(name="Open", type="checking"))
    closed = await create_account(
        db_session, user, AccountCreate(name="Closed", type="checking", is_active=False)
    )
    data = TransactionCreate(
        type="transfer",
        source=source,
        description="History",
        postings=[
            PostingCreate(
                account_id=active.id, source_amount=100, base_amount_pln=100, direction="debit"
            ),
            PostingCreate(
                account_id=closed.id, source_amount=100, base_amount_pln=100, direction="credit"
            ),
        ],
    )
    kwargs = {"allow_inactive_accounts": True} if allow_history else {}
    if accepted:
        await create_transaction(db_session, user, data, **kwargs)
    else:
        with pytest.raises(ValueError):
            await create_transaction(db_session, user, data, **kwargs)
    assert closed.is_active is False
    assert await db_session.scalar(select(func.count(FinancialTransaction.id))) == int(accepted)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["foreign-account", "currency", "posting-sum"])
async def test_history_opt_in_preserves_other_ledger_checks(
    db_session: AsyncSession, fault: str
) -> None:
    user = uuid.uuid4()
    active = await create_account(db_session, user, AccountCreate(name="Open", type="checking"))
    closed = await create_account(
        db_session,
        uuid.uuid4() if fault == "foreign-account" else user,
        AccountCreate(name="Closed", type="checking", is_active=False),
    )
    data = TransactionCreate(
        type="transfer",
        source="actual",
        description="Invalid history",
        postings=[
            PostingCreate(
                account_id=active.id, source_amount=100, base_amount_pln=100, direction="debit"
            ),
            PostingCreate(
                account_id=closed.id,
                source_amount=99 if fault == "posting-sum" else 100,
                base_amount_pln=99 if fault == "posting-sum" else 100,
                source_currency="USD" if fault == "currency" else "PLN",
                direction="credit",
            ),
        ],
    )
    with pytest.raises(ValueError):
        await create_transaction(db_session, user, data, allow_inactive_accounts=True)
    assert await db_session.scalar(select(func.count(FinancialTransaction.id))) == 0
    assert closed.is_active is False


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "was_active,source_active", [(True, True), (True, False), (False, True), (False, False)]
)
async def test_resolve_never_reopens_mapped_account(
    db_session: AsyncSession, was_active: bool, source_active: bool
) -> None:
    user = uuid.uuid4()
    account = await create_account(
        db_session, user, AccountCreate(name="Local name", type="checking", is_active=was_active)
    )
    account.closed_at = date(2026, 1, 1) if not was_active else None
    closed_at = account.closed_at
    await importer._store_mapping(db_session, user, "account", "a", account.id)
    parser = SimpleNamespace(
        get_accounts=lambda: [
            {
                "actual_id": "a",
                "name": "Source name",
                "type": "checking",
                "currency": "PLN",
                "is_budget_account": True,
                "is_active": source_active,
            }
        ],
        get_categories=list,
        get_category_groups=list,
    )
    for _ in range(2):
        mapping, _, _, _, _ = await importer.resolve_ids(db_session, user, parser, [])
        assert mapping == {"a": account.id}
        assert account.is_active is (was_active and source_active)
        assert account.closed_at == closed_at and account.name == "Local name"
        assert await db_session.scalar(select(func.count(Account.id))) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_migrate_closed_history_reconciles_and_repeats_without_reopening(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = make_closed_export(tmp_path)
    archive = tmp_path / "export.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.write(source, "db.sqlite")

    @asynccontextmanager
    async def session_scope() -> AsyncIterator[AsyncSession]:
        yield db_session

    monkeypatch.setattr(importer, "async_session_factory", session_scope)
    monkeypatch.setattr(importer.tempfile, "gettempdir", lambda: str(tmp_path))
    user = uuid.uuid4()
    for _ in range(2):
        await importer.migrate(archive, user, require_reconciled=True)
        accounts = list((await db_session.execute(select(Account))).scalars())
        assert len(accounts) == 3
        assert {a.name: a.is_active for a in accounts} == {
            "Open PLN": True,
            "Closed PLN": False,
            "Empty closed": False,
        }
        assert all(a.closed_at is None for a in accounts)  # do not invent closure dates
        assert await db_session.scalar(select(func.count(FinancialTransaction.id))) == 4
        report = json.loads((tmp_path / "actual_migration/reconciliation.json").read_text())
        assert report["is_reconciled"] is True and report["import_errors"] == []


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("mapped_before", [False, True])
async def test_failed_reconciliation_rolls_back_closed_history_from_fresh_session(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mapped_before: bool
) -> None:
    source = make_closed_export(tmp_path)
    # A real orphan transfer leg changes the source balance but cannot be
    # reconstructed; strict reconciliation must reject the entire import.
    with sqlite3.connect(source) as conn:
        conn.execute(
            "INSERT INTO transactions VALUES ('orphan','closed',NULL,1,NULL,NULL,NULL,20261005,0,0,0,NULL,'missing')"
        )
    archive = tmp_path / "export.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.write(source, "db.sqlite")
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    user = uuid.uuid4()
    if mapped_before:
        async with factory() as seed:
            account = await create_account(
                seed, user, AccountCreate(name="Existing", type="savings", is_budget_account=False)
            )
            await importer._store_mapping(seed, user, "account", "closed", account.id)
            await seed.commit()
    monkeypatch.setattr(importer, "async_session_factory", factory)
    monkeypatch.setattr(importer.tempfile, "gettempdir", lambda: str(tmp_path))
    with pytest.raises(ReconciliationError):
        await importer.migrate(archive, user, require_reconciled=True)
    async with factory() as fresh:
        assert await fresh.scalar(select(func.count(Account.id))) == int(mapped_before)
        assert await fresh.scalar(select(func.count(ActualImportMapping.id))) == int(mapped_before)
        assert await fresh.scalar(select(func.count(FinancialTransaction.id))) == 0
        if mapped_before:
            stored = await fresh.scalar(select(Account))
            assert stored is not None and stored.is_active is True and stored.name == "Existing"
