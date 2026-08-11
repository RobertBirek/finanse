import os
import sqlite3
import tempfile
from pathlib import Path

from app.finance.actual_parser import ActualParser


def _make_actual_db(schema_sql: str, inserts: list[str]) -> Path:
    conn = sqlite3.connect(":memory:")
    conn.executescript(schema_sql)
    for stmt in inserts:
        conn.execute(stmt)
    conn.commit()
    tmp_file = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp_path = Path(tmp_file.name)
    tmp_file.close()
    src = sqlite3.connect(str(tmp_path))
    conn.backup(src)
    conn.close()
    src.close()
    return tmp_path


class TestActualParserAccounts:
    def test_reads_active_accounts(self):
        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        """
        inserts = [
            "INSERT INTO accounts VALUES ('a1', 'ING', 0, 0, 0)",
            "INSERT INTO accounts VALUES ('a2', 'Gotowka', 1, 0, 0)",
            "INSERT INTO accounts VALUES ('a3', 'Zamkniete', 0, 1, 0)",
            "INSERT INTO accounts VALUES ('a4', 'Usuniete', 0, 0, 1)",
        ]
        db_path = _make_actual_db(schema, inserts)

        try:
            parser = ActualParser(db_path)
            result = parser.get_accounts()
            by_id = {a["actual_id"]: a for a in result}

            assert len(result) == 2
            assert by_id["a1"]["name"] == "ING"
            assert by_id["a1"]["type"] == "checking"
            assert by_id["a2"]["name"] == "Gotowka"
            assert by_id["a2"]["type"] == "savings"
        finally:
            os.unlink(db_path)

    def test_currency_detection(self):
        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        """
        inserts = [
            "INSERT INTO accounts VALUES ('a1', 'Revolut EUR', 0, 0, 0)",
            "INSERT INTO accounts VALUES ('a2', 'Revolut USD', 0, 0, 0)",
            "INSERT INTO accounts VALUES ('a3', 'ING', 0, 0, 0)",
            "INSERT INTO accounts VALUES ('a4', 'neutralny', 0, 0, 0)",
            "INSERT INTO accounts VALUES ('a5', 'EUropejski', 0, 0, 0)",
        ]
        db_path = _make_actual_db(schema, inserts)

        try:
            parser = ActualParser(db_path)
            result = parser.get_accounts()
            by_name = {a["name"]: a for a in result}

            assert by_name["Revolut EUR"]["currency"] == "EUR"
            assert by_name["Revolut USD"]["currency"] == "USD"
            assert by_name["ING"]["currency"] == "PLN"
            assert by_name["neutralny"]["currency"] == "PLN"
            assert by_name["EUropejski"]["currency"] == "PLN"
        finally:
            os.unlink(db_path)

    def test_null_safe_currency(self):
        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        """
        inserts = [
            "INSERT INTO accounts VALUES ('a1', NULL, 0, 0, 0)",
        ]
        db_path = _make_actual_db(schema, inserts)

        try:
            parser = ActualParser(db_path)
            result = parser.get_accounts()
            assert len(result) == 1
            assert result[0]["currency"] == "PLN"
        finally:
            os.unlink(db_path)

    def test_context_manager(self):
        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        """
        inserts = [
            "INSERT INTO accounts VALUES ('a1', 'ING', 0, 0, 0)",
        ]
        db_path = _make_actual_db(schema, inserts)

        try:
            with ActualParser(db_path) as parser:
                result = parser.get_accounts()
                assert len(result) == 1
        finally:
            os.unlink(db_path)


class TestActualParserCategories:
    def test_reads_categories_with_groups(self):
        schema = """
        CREATE TABLE categories (id TEXT, name TEXT, is_income INTEGER, cat_group TEXT, tombstone INTEGER);
        CREATE TABLE category_groups (id TEXT, name TEXT);
        """
        inserts = [
            "INSERT INTO category_groups VALUES ('g1', 'Wydatki biezace')",
            "INSERT INTO category_groups VALUES ('g2', 'Przychody')",
            "INSERT INTO categories VALUES ('c1', 'Jedzenie', 0, 'g1', 0)",
            "INSERT INTO categories VALUES ('c2', 'Pensja', 1, 'g2', 0)",
            "INSERT INTO categories VALUES ('c3', 'Ukryta', 0, 'g1', 1)",
        ]
        db_path = _make_actual_db(schema, inserts)

        try:
            parser = ActualParser(db_path)
            result = parser.get_categories()
            by_id = {c["actual_id"]: c for c in result}

            assert len(result) == 2
            assert by_id["c1"]["name"] == "Jedzenie"
            assert by_id["c1"]["type"] == "expense"
            assert by_id["c2"]["name"] == "Pensja"
            assert by_id["c2"]["type"] == "income"
        finally:
            os.unlink(db_path)


class TestActualParserTransactions:
    def test_reads_simple_expense(self):
        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        CREATE TABLE categories (id TEXT, name TEXT, is_income INTEGER, cat_group TEXT, tombstone INTEGER);
        CREATE TABLE transactions (
            id TEXT, isParent INTEGER, isChild INTEGER, parent_id TEXT,
            acct TEXT, category TEXT, amount INTEGER, description TEXT,
            notes TEXT, date INTEGER, transferred_id TEXT, tombstone INTEGER
        );
        CREATE TABLE payees (id TEXT, name TEXT);
        CREATE TABLE payee_mapping (id TEXT, targetId TEXT, payeeId TEXT);
        """
        inserts = [
            "INSERT INTO accounts VALUES ('acc1', 'ING', 0, 0, 0)",
            "INSERT INTO accounts VALUES ('acc2', 'Gotowka', 0, 0, 0)",
            "INSERT INTO categories VALUES ('cat1', 'Jedzenie', 0, 'g1', 0)",
            "INSERT INTO payees VALUES ('pay1', 'Biedronka')",
            "INSERT INTO payee_mapping VALUES ('pm1', 'tx1', 'pay1')",
            "INSERT INTO transactions VALUES ('tx1', 0, 0, NULL, 'acc1', 'cat1', -5000, 'pm1', 'notatka', 20260715, NULL, 0)",
        ]
        db_path = _make_actual_db(schema, inserts)

        try:
            with ActualParser(db_path) as parser:
                result = parser.get_transactions()
                assert len(result) == 1
                txn = result[0]
                assert txn["type"] == "expense"
                assert str(txn["date"]) == "2026-07-15"
                assert str(txn["date"]) != "1970-01-01"
                assert "Biedronka" in txn["description"]
                assert txn["postings"][0]["account_actual_id"] == "acc1"
                assert txn["postings"][0]["direction"] == "credit"
                assert txn["postings"][0]["source_amount"] == 5000
                assert txn["postings"][1]["account_actual_id"] == "acc1"
                assert txn["postings"][1]["category_actual_id"] == "cat1"
                assert txn["postings"][1]["direction"] == "debit"
                assert txn["postings"][1]["source_amount"] == 5000
        finally:
            os.unlink(db_path)

    def test_reads_simple_income(self):
        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        CREATE TABLE categories (id TEXT, name TEXT, is_income INTEGER, cat_group TEXT, tombstone INTEGER);
        CREATE TABLE transactions (
            id TEXT, isParent INTEGER, isChild INTEGER, parent_id TEXT,
            acct TEXT, category TEXT, amount INTEGER, description TEXT,
            notes TEXT, date INTEGER, transferred_id TEXT, tombstone INTEGER
        );
        CREATE TABLE payees (id TEXT, name TEXT);
        CREATE TABLE payee_mapping (id TEXT, targetId TEXT, payeeId TEXT);
        """
        inserts = [
            "INSERT INTO accounts VALUES ('acc1', 'ING', 0, 0, 0)",
            "INSERT INTO categories VALUES ('cat1', 'Pensja', 1, 'g2', 0)",
            "INSERT INTO payees VALUES ('pay1', 'Pracodawca')",
            "INSERT INTO payee_mapping VALUES ('pm1', 'tx1', 'pay1')",
            "INSERT INTO transactions VALUES ('tx1', 0, 0, NULL, 'acc1', 'cat1', 500000, 'pm1', NULL, 20260715, NULL, 0)",
        ]
        db_path = _make_actual_db(schema, inserts)

        try:
            with ActualParser(db_path) as parser:
                result = parser.get_transactions()
                assert len(result) == 1
                txn = result[0]
                assert txn["type"] == "income"
                assert txn["postings"][0]["direction"] == "debit"
                assert txn["postings"][1]["direction"] == "credit"
                assert txn["postings"][0]["source_amount"] == 500000
        finally:
            os.unlink(db_path)

    def test_skips_zero_amount(self):
        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        CREATE TABLE categories (id TEXT, name TEXT, is_income INTEGER, cat_group TEXT, tombstone INTEGER);
        CREATE TABLE transactions (
            id TEXT, isParent INTEGER, isChild INTEGER, parent_id TEXT,
            acct TEXT, category TEXT, amount INTEGER, description TEXT,
            notes TEXT, date INTEGER, transferred_id TEXT, tombstone INTEGER
        );
        CREATE TABLE payees (id TEXT, name TEXT);
        CREATE TABLE payee_mapping (id TEXT, targetId TEXT, payeeId TEXT);
        """
        inserts = [
            "INSERT INTO accounts VALUES ('acc1', 'ING', 0, 0, 0)",
            "INSERT INTO categories VALUES ('cat1', 'Jedzenie', 0, 'g1', 0)",
            "INSERT INTO transactions VALUES ('tx1', 0, 0, NULL, 'acc1', 'cat1', 0, NULL, NULL, 20260715, NULL, 0)",
        ]
        db_path = _make_actual_db(schema, inserts)

        try:
            with ActualParser(db_path) as parser:
                result = parser.get_transactions()
                assert len(result) == 0
        finally:
            os.unlink(db_path)

    def test_unmatched_payee(self):
        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        CREATE TABLE categories (id TEXT, name TEXT, is_income INTEGER, cat_group TEXT, tombstone INTEGER);
        CREATE TABLE transactions (
            id TEXT, isParent INTEGER, isChild INTEGER, parent_id TEXT,
            acct TEXT, category TEXT, amount INTEGER, description TEXT,
            notes TEXT, date INTEGER, transferred_id TEXT, tombstone INTEGER
        );
        CREATE TABLE payees (id TEXT, name TEXT);
        CREATE TABLE payee_mapping (id TEXT, targetId TEXT, payeeId TEXT);
        """
        inserts = [
            "INSERT INTO accounts VALUES ('acc1', 'ING', 0, 0, 0)",
            "INSERT INTO categories VALUES ('cat1', 'Jedzenie', 0, 'g1', 0)",
            # no payee_mapping row for 'missing_pm'
            "INSERT INTO transactions VALUES ('tx1', 0, 0, NULL, 'acc1', 'cat1', -5000, 'missing_pm', NULL, 20260715, NULL, 0)",
        ]
        db_path = _make_actual_db(schema, inserts)

        try:
            with ActualParser(db_path) as parser:
                result = parser.get_transactions()
                assert len(result) == 1
                txn = result[0]
                assert txn["description"] == "(no description)"
        finally:
            os.unlink(db_path)

    def test_reconstructs_transfer(self):
        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        CREATE TABLE transactions (
            id TEXT, isParent INTEGER, isChild INTEGER, parent_id TEXT,
            acct TEXT, category TEXT, amount INTEGER, description TEXT,
            notes TEXT, date INTEGER, transferred_id TEXT, tombstone INTEGER
        );
        """
        inserts = [
            "INSERT INTO accounts VALUES ('acc_ing', 'ING', 0, 0, 0)",
            "INSERT INTO accounts VALUES ('acc_cash', 'Gotowka', 0, 0, 0)",
            "INSERT INTO transactions VALUES ('tx_a', 0, 0, NULL, 'acc_ing', NULL, -10000, NULL, NULL, 20260701, 'link_1', 0)",
            "INSERT INTO transactions VALUES ('tx_b', 0, 0, NULL, 'acc_cash', NULL, 10000, NULL, NULL, 20260701, 'link_1', 0)",
        ]
        db_path = _make_actual_db(schema, inserts)

        try:
            with ActualParser(db_path) as parser:
                result = parser.get_transfers()
                assert len(result) == 1
                txn = result[0]
                assert txn["type"] == "transfer"
                assert txn["description"] == "Transfer: ING → Gotowka"
                assert len(txn["postings"]) == 2
                assert txn["postings"][0]["account_actual_id"] == "acc_ing"
                assert txn["postings"][0]["direction"] == "credit"
                assert txn["postings"][0]["source_amount"] == 10000
                assert txn["postings"][1]["account_actual_id"] == "acc_cash"
                assert txn["postings"][1]["direction"] == "debit"
                assert txn["postings"][1]["source_amount"] == 10000
        finally:
            os.unlink(db_path)
