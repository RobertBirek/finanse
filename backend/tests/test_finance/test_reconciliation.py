import json
import sqlite3
import sys
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.finance.actual_parser import ActualParser
from app.finance.reconciliation import (
    CategoryBalance,
    ReconciliationError,
    ReconciliationReport,
    SourceBalance,
    reconcile_account_balances,
    reconcile_category_balances,
    require_reconciled,
)


def test_reports_source_balance_difference():
    expected = {
        "actual-account-1": SourceBalance(
            actual_id="actual-account-1",
            name="ING",
            currency="PLN",
            is_budget_account=True,
            amount=109805,
        )
    }
    actual = {
        "actual-account-1": SourceBalance(
            actual_id="actual-account-1",
            name="ING",
            currency="PLN",
            is_budget_account=True,
            amount=109800,
        )
    }

    report = reconcile_account_balances(expected, actual)

    assert report.accounts[0].difference == 5
    assert report.is_reconciled is False


def test_parser_sums_active_transaction_legs_per_account(tmp_path):
    db_path = tmp_path / "actual.sqlite"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        CREATE TABLE transactions (
            id TEXT, isParent INTEGER, isChild INTEGER, parent_id TEXT,
            acct TEXT, category TEXT, amount INTEGER, description TEXT,
            notes TEXT, date INTEGER, transferred_id TEXT, tombstone INTEGER
        );
        INSERT INTO accounts VALUES ('ing', 'ING', 0, 0, 0);
        INSERT INTO accounts VALUES ('loan', 'Loan', 1, 0, 0);
        INSERT INTO accounts VALUES ('closed', 'Closed', 0, 1, 0);
        INSERT INTO transactions VALUES ('income', 0, 0, NULL, 'ing', NULL, 120000, NULL, NULL, 20260814, NULL, 0);
        INSERT INTO transactions VALUES ('expense', 0, 0, NULL, 'ing', NULL, -20195, NULL, NULL, 20260814, NULL, 0);
        INSERT INTO transactions VALUES ('loan-txn', 0, 0, NULL, 'loan', NULL, -5000, NULL, NULL, 20260814, NULL, 0);
        INSERT INTO transactions VALUES ('split-child', 0, 1, 'split-parent', 'ing', NULL, -99999, NULL, NULL, 20260814, NULL, 0);
        INSERT INTO transactions VALUES ('deleted', 0, 0, NULL, 'ing', NULL, 99999, NULL, NULL, 20260814, NULL, 1);
        """
    )
    connection.close()

    with ActualParser(db_path) as parser:
        balances = parser.get_account_balances()

    assert balances == {
        "ing": SourceBalance("ing", "ING", "PLN", True, 99805),
        "loan": SourceBalance("loan", "Loan", "PLN", False, -5000),
    }


def test_require_reconciled_rejects_a_balance_difference():
    report = reconcile_account_balances(
        {"actual-account-1": SourceBalance("actual-account-1", "ING", "PLN", True, 109805)},
        {"actual-account-1": SourceBalance("actual-account-1", "ING", "PLN", True, 109800)},
    )

    with pytest.raises(ReconciliationError, match="not reconciled"):
        require_reconciled(report)


def test_report_fails_closed_on_import_error_despite_reconciled_account_and_category_rows():
    accounts = reconcile_account_balances(
        {"actual-account-1": SourceBalance("actual-account-1", "ING", "PLN", True, 109805)},
        {"actual-account-1": SourceBalance("actual-account-1", "ING", "PLN", True, 109805)},
    ).accounts
    categories = reconcile_category_balances(
        {"food": CategoryBalance("food", "Food", "expense", -5000)},
        {"food": CategoryBalance("food", "Food", "expense", -5000)},
    )
    report = ReconciliationReport(
        accounts=accounts,
        categories=categories,
        import_errors=("Skipped expense-1: Missing FX rate: USD on 2026-08-14",),
    )

    assert report.is_reconciled is False
    assert report.to_dict()["import_errors"] == [
        "Skipped expense-1: Missing FX rate: USD on 2026-08-14"
    ]
    assert "Categories:" in report.to_text()
    assert "Import errors:" in report.to_text()
    with pytest.raises(ReconciliationError, match="not reconciled"):
        require_reconciled(report)


def test_report_fails_closed_on_category_discrepancy():
    accounts = reconcile_account_balances({}, {}).accounts
    categories = reconcile_category_balances(
        {"food": CategoryBalance("food", "Food", "expense", -5000)},
        {"food": CategoryBalance("food", "Food", "expense", -4995)},
    )

    report = ReconciliationReport(accounts=accounts, categories=categories)

    assert report.categories[0].difference == -5
    assert report.is_reconciled is False


def test_report_fails_closed_and_exposes_currency_budget_and_mapping_mismatches():
    report = reconcile_account_balances(
        {"actual-ing": SourceBalance("actual-ing", "ING", "PLN", True, 109805)},
        {
            "actual-ing": SourceBalance("actual-ing", "ING", "EUR", False, 109805),
            "pa-only": SourceBalance("pa-only", "Cash", "PLN", True, 100),
        },
    )

    assert report.is_reconciled is False
    assert report.accounts[0].is_reconciled is False
    assert report.accounts[0].to_dict()["actual_amount"] is None
    assert report.accounts[1].to_dict()["pa_currency"] == "EUR"
    assert report.accounts[1].to_dict()["pa_is_budget_account"] is False


def test_report_serializes_json_data_and_human_readable_rows():
    report = reconcile_account_balances(
        {"actual-account-1": SourceBalance("actual-account-1", "ING", "PLN", True, 109805)},
        {"actual-account-1": SourceBalance("actual-account-1", "ING", "PLN", True, 109805)},
    )

    assert report.to_dict() == {
        "is_reconciled": True,
        "accounts": [
            {
                "actual_id": "actual-account-1",
                "actual_name": "ING",
                "pa_name": "ING",
                "currency": "PLN",
                "is_budget_account": True,
                "pa_currency": "PLN",
                "pa_is_budget_account": True,
                "actual_amount": 109805,
                "pa_amount": 109805,
                "difference": 0,
                "is_reconciled": True,
            }
        ],
        "categories": [],
        "import_errors": [],
    }
    assert report.to_text() == "ING | PLN | budget | Actual 109805 | PA 109805 | diff 0 | OK"


@pytest.mark.asyncio
async def test_cli_forwards_require_reconciled_to_migration(tmp_path, monkeypatch):
    from scripts import migrate_actual

    blob_path = tmp_path / "actual.blob"
    blob_path.touch()
    user_id = uuid.uuid4()
    migrate = AsyncMock()
    monkeypatch.setattr(migrate_actual, "migrate", migrate)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "migrate_actual.py",
            "--blob-path",
            str(blob_path),
            "--user-id",
            str(user_id),
            "--dry-run",
            "--require-reconciled",
        ],
    )

    await migrate_actual.main()

    migrate.assert_awaited_once_with(
        blob_path,
        user_id,
        dry_run=True,
        require_reconciled=True,
    )


def test_importer_writes_reconciliation_json_and_text_reports(tmp_path):
    from scripts.migrate_actual import write_reconciliation_report

    report = reconcile_account_balances(
        {"actual-account-1": SourceBalance("actual-account-1", "ING", "PLN", True, 109805)},
        {"actual-account-1": SourceBalance("actual-account-1", "ING", "PLN", True, 109805)},
    )

    write_reconciliation_report(tmp_path, report)

    assert json.loads((tmp_path / "reconciliation.json").read_text()) == report.to_dict()
    assert (tmp_path / "reconciliation_report.txt").read_text() == report.to_text() + "\n"


@pytest.mark.asyncio
async def test_pa_source_balances_use_only_mapped_account_postings():
    from scripts.migrate_actual import get_pa_source_balances

    account_id = uuid.uuid4()

    class AccountResult:
        def scalars(self):
            return self

        def all(self):
            return [
                SimpleNamespace(
                    id=account_id,
                    name="ING",
                    currency="PLN",
                    is_budget_account=True,
                )
            ]

    class PostingResult:
        def all(self):
            return [(account_id, 109805)]

    class Database:
        def __init__(self):
            self.results = [AccountResult(), PostingResult()]

        async def execute(self, statement):
            return self.results.pop(0)

    balances = await get_pa_source_balances(
        Database(),
        uuid.uuid4(),
        {"actual-ing": account_id, "unmapped": uuid.uuid4()},
    )

    assert balances == {
        "actual-ing": SourceBalance("actual-ing", "ING", "PLN", True, 109805),
    }


@pytest.mark.asyncio
async def test_dry_run_require_reconciled_writes_reports_then_fails_closed(tmp_path, monkeypatch):
    from scripts import migrate_actual

    sqlite_path = tmp_path / "actual.sqlite"
    connection = sqlite3.connect(sqlite_path)
    connection.executescript(
        """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        CREATE TABLE categories (id TEXT, name TEXT, is_income INTEGER, cat_group TEXT, tombstone INTEGER);
        CREATE TABLE transactions (
            id TEXT, isParent INTEGER, isChild INTEGER, parent_id TEXT,
            acct TEXT, category TEXT, amount INTEGER, description TEXT,
            notes TEXT, date INTEGER, transferred_id TEXT, tombstone INTEGER
        );
        CREATE TABLE payees (id TEXT, name TEXT);
        CREATE TABLE payee_mapping (id TEXT, targetId TEXT, payeeId TEXT);
        INSERT INTO accounts VALUES ('ing', 'ING', 0, 0, 0);
        INSERT INTO categories VALUES ('income', 'Income', 1, NULL, 0);
        INSERT INTO transactions VALUES ('income', 0, 0, NULL, 'ing', 'income', 109805, NULL, NULL, 20260814, NULL, 0);
        """
    )
    connection.close()
    monkeypatch.setattr(migrate_actual, "extract_sqlite", AsyncMock(return_value=sqlite_path))
    monkeypatch.setattr(
        migrate_actual,
        "NbpRateProvider",
        lambda: SimpleNamespace(close=AsyncMock()),
    )
    monkeypatch.setattr(migrate_actual.tempfile, "gettempdir", lambda: str(tmp_path))

    with pytest.raises(ReconciliationError, match="not reconciled"):
        await migrate_actual.migrate(
            tmp_path / "unused.blob",
            uuid.uuid4(),
            dry_run=True,
            require_reconciled=True,
        )

    output_dir = tmp_path / "actual_migration"
    assert (output_dir / "reconciliation.json").exists()
    assert "MISMATCH" in (output_dir / "reconciliation_report.txt").read_text()
    report = json.loads((output_dir / "reconciliation.json").read_text())
    assert report["categories"] == [
        {
            "actual_id": "income",
            "actual_name": "Income",
            "pa_name": None,
            "type": "income",
            "pa_type": None,
            "actual_amount_pln": 109805,
            "pa_amount_pln": None,
            "difference": None,
            "is_reconciled": False,
        }
    ]


@pytest.mark.asyncio
async def test_dry_run_reconciliation_report_includes_skipped_missing_fx_transaction(
    tmp_path, monkeypatch
):
    from scripts import migrate_actual

    sqlite_path = tmp_path / "actual.sqlite"
    connection = sqlite3.connect(sqlite_path)
    connection.executescript(
        """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        CREATE TABLE categories (id TEXT, name TEXT, is_income INTEGER, cat_group TEXT, tombstone INTEGER);
        CREATE TABLE transactions (
            id TEXT, isParent INTEGER, isChild INTEGER, parent_id TEXT,
            acct TEXT, category TEXT, amount INTEGER, description TEXT,
            notes TEXT, date INTEGER, transferred_id TEXT, tombstone INTEGER
        );
        CREATE TABLE payees (id TEXT, name TEXT);
        CREATE TABLE payee_mapping (id TEXT, targetId TEXT, payeeId TEXT);
        INSERT INTO accounts VALUES ('usd', 'Revolut USD', 0, 0, 0);
        INSERT INTO categories VALUES ('food', 'Food', 0, NULL, 0);
        INSERT INTO transactions VALUES ('expense-1', 0, 0, NULL, 'usd', 'food', -500, NULL, NULL, 20260814, NULL, 0);
        """
    )
    connection.close()
    monkeypatch.setattr(migrate_actual, "extract_sqlite", AsyncMock(return_value=sqlite_path))
    monkeypatch.setattr(
        migrate_actual,
        "NbpRateProvider",
        lambda: SimpleNamespace(get_rate=AsyncMock(return_value=0.0), close=AsyncMock()),
    )
    monkeypatch.setattr(migrate_actual.tempfile, "gettempdir", lambda: str(tmp_path))

    await migrate_actual.migrate(tmp_path / "unused.blob", uuid.uuid4(), dry_run=True)

    report = json.loads((tmp_path / "actual_migration" / "reconciliation.json").read_text())
    assert report["import_errors"] == ["Skipped expense-1: Missing FX rate: USD on 2026-08-14"]
