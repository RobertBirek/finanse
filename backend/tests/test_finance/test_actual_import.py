import os
import sqlite3
import tempfile
from pathlib import Path

from app.finance.actual_parser import ActualParser
from app.finance.models import Category


def _make_actual_db(schema_sql: str, inserts: list[str]) -> Path:
    conn = sqlite3.connect(":memory:")
    conn.executescript(schema_sql)
    for stmt in inserts:
        conn.execute(stmt)
    conn.commit()
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp_file:
        tmp_path = Path(tmp_file.name)
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
            assert by_id["a1"]["is_budget_account"] is True
            assert by_id["a2"]["name"] == "Gotowka"
            assert by_id["a2"]["type"] == "savings"
            assert by_id["a2"]["is_budget_account"] is False
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
        CREATE TABLE category_groups (id TEXT, name TEXT, tombstone INTEGER);
        """
        inserts = [
            "INSERT INTO category_groups VALUES ('g1', 'Wydatki biezace', 0)",
            "INSERT INTO category_groups VALUES ('g2', 'Przychody', 0)",
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
            assert by_id["c1"]["group_actual_id"] == "g1"
            assert by_id["c2"]["name"] == "Pensja"
            assert by_id["c2"]["type"] == "income"
            assert by_id["c2"]["group_actual_id"] == "g2"
            assert parser.get_category_groups() == [
                {"actual_id": "g2", "name": "Przychody", "type": "income"},
                {"actual_id": "g1", "name": "Wydatki biezace", "type": "expense"},
            ]
        finally:
            os.unlink(db_path)

    def test_skips_tombstoned_groups_with_active_children(self):
        schema = """
        CREATE TABLE categories (id TEXT, name TEXT, is_income INTEGER, cat_group TEXT, tombstone INTEGER);
        CREATE TABLE category_groups (id TEXT, name TEXT, tombstone INTEGER);
        """
        inserts = [
            "INSERT INTO category_groups VALUES ('g_active', 'Aktywna', 0)",
            "INSERT INTO category_groups VALUES ('g_deleted', 'Usunieta', 1)",
            "INSERT INTO categories VALUES ('c_active', 'Paliwo', 0, 'g_active', 0)",
            "INSERT INTO categories VALUES ('c_deleted_group', 'Czynsz', 0, 'g_deleted', 0)",
        ]
        db_path = _make_actual_db(schema, inserts)

        try:
            with ActualParser(db_path) as parser:
                assert parser.get_category_groups() == [
                    {"actual_id": "g_active", "name": "Aktywna", "type": "expense"}
                ]
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
        CREATE TABLE payees (id TEXT, name TEXT);
        CREATE TABLE payee_mapping (id TEXT, targetId TEXT, payeeId TEXT);
        """
        inserts = [
            "INSERT INTO accounts VALUES ('acc_ing', 'ING', 0, 0, 0)",
            "INSERT INTO accounts VALUES ('acc_cash', 'Gotowka', 0, 0, 0)",
            "INSERT INTO transactions VALUES ('tx_a', 0, 0, NULL, 'acc_ing', NULL, -10000, NULL, NULL, 20260701, 'tx_b', 0)",
            "INSERT INTO transactions VALUES ('tx_b', 0, 0, NULL, 'acc_cash', NULL, 10000, NULL, NULL, 20260701, 'tx_a', 0)",
        ]
        db_path = _make_actual_db(schema, inserts)

        try:
            with ActualParser(db_path) as parser:
                result = parser.get_transfers()
                assert len(result) == 1
                txn = result[0]
                assert txn["type"] == "transfer"
                assert txn["description"] == "Transfer: ING -> Gotowka"
                assert len(txn["postings"]) == 2
                assert txn["postings"][0]["account_actual_id"] == "acc_ing"
                assert txn["postings"][0]["direction"] == "credit"
                assert txn["postings"][0]["source_amount"] == 10000
                assert txn["postings"][1]["account_actual_id"] == "acc_cash"
                assert txn["postings"][1]["direction"] == "debit"
                assert txn["postings"][1]["source_amount"] == 10000
        finally:
            os.unlink(db_path)

    def test_preserves_each_transfer_side_amount_and_currency(self):
        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        CREATE TABLE transactions (
            id TEXT, isParent INTEGER, isChild INTEGER, parent_id TEXT,
            acct TEXT, category TEXT, amount INTEGER, description TEXT,
            notes TEXT, date INTEGER, transferred_id TEXT, tombstone INTEGER
        );
        """
        inserts = [
            "INSERT INTO accounts VALUES ('acc_pln', 'ING', 0, 0, 0)",
            "INSERT INTO accounts VALUES ('acc_usd', 'Revolut USD', 0, 0, 0)",
            "INSERT INTO transactions VALUES ('tx_pln', 0, 0, NULL, 'acc_pln', NULL, -43210, NULL, NULL, 20260701, 'tx_usd', 0)",
            "INSERT INTO transactions VALUES ('tx_usd', 0, 0, NULL, 'acc_usd', NULL, 12345, NULL, NULL, 20260701, 'tx_pln', 0)",
        ]
        db_path = _make_actual_db(schema, inserts)

        try:
            with ActualParser(db_path) as parser:
                postings = parser.get_transfers()[0]["postings"]
                assert postings == [
                    {
                        "account_actual_id": "acc_pln",
                        "category_actual_id": None,
                        "source_amount": 43210,
                        "source_currency": "PLN",
                        "direction": "credit",
                    },
                    {
                        "account_actual_id": "acc_usd",
                        "category_actual_id": None,
                        "source_amount": 12345,
                        "source_currency": "USD",
                        "direction": "debit",
                    },
                ]
        finally:
            os.unlink(db_path)

    def test_reconstructs_transfer_from_view_schema_with_real_currency_values(self):
        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        CREATE TABLE transaction_rows (
            id TEXT, account TEXT, category TEXT, amount INTEGER, payee TEXT,
            notes TEXT, date INTEGER, transfer_id TEXT, tombstone INTEGER,
            is_parent INTEGER, is_child INTEGER, parent_id TEXT
        );
        CREATE VIEW v_transactions AS
        SELECT id, account, category, amount, payee, notes, date, transfer_id,
               tombstone, is_parent, is_child, parent_id
        FROM transaction_rows;
        """
        inserts = [
            "INSERT INTO accounts VALUES ('acc_pln', 'ING', 0, 0, 0)",
            "INSERT INTO accounts VALUES ('acc_usd', 'Revolut USD', 0, 0, 0)",
            "INSERT INTO transaction_rows VALUES ('tx_pln', 'acc_pln', NULL, -43210, NULL, NULL, 20260701, 'tx_usd', 0, 0, 0, NULL)",
            "INSERT INTO transaction_rows VALUES ('tx_usd', 'acc_usd', NULL, 12345, NULL, NULL, 20260701, 'tx_pln', 0, 0, 0, NULL)",
        ]
        db_path = _make_actual_db(schema, inserts)

        try:
            with ActualParser(db_path) as parser:
                assert parser._use_view is True
                assert parser.get_transfers()[0]["postings"] == [
                    {
                        "account_actual_id": "acc_pln",
                        "category_actual_id": None,
                        "source_amount": 43210,
                        "source_currency": "PLN",
                        "direction": "credit",
                    },
                    {
                        "account_actual_id": "acc_usd",
                        "category_actual_id": None,
                        "source_amount": 12345,
                        "source_currency": "USD",
                        "direction": "debit",
                    },
                ]
        finally:
            os.unlink(db_path)

    def test_transfer_with_warnings(self):
        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        CREATE TABLE transactions (
            id TEXT, isParent INTEGER, isChild INTEGER, parent_id TEXT,
            acct TEXT, category TEXT, amount INTEGER, description TEXT,
            notes TEXT, date INTEGER, transferred_id TEXT, tombstone INTEGER
        );
        CREATE TABLE payees (id TEXT, name TEXT);
        CREATE TABLE payee_mapping (id TEXT, targetId TEXT, payeeId TEXT);
        """
        inserts = [
            "INSERT INTO accounts VALUES ('acc_ing', 'ING', 0, 0, 0)",
            "INSERT INTO accounts VALUES ('acc_cash', 'Gotowka', 0, 0, 0)",
            # Mismatched amounts: tx_c sends 10000 but tx_d receives only 5000
            "INSERT INTO transactions VALUES ('tx_c', 0, 0, NULL, 'acc_ing', NULL, -10000, NULL, NULL, 20260701, 'tx_d', 0)",
            "INSERT INTO transactions VALUES ('tx_d', 0, 0, NULL, 'acc_cash', NULL, 5000, NULL, NULL, 20260701, 'tx_c', 0)",
            # Orphan row: transferred_id points to non-existent row
            "INSERT INTO transactions VALUES ('tx_e', 0, 0, NULL, 'acc_ing', NULL, -3000, NULL, NULL, 20260701, 'tx_nonexist', 0)",
        ]
        db_path = _make_actual_db(schema, inserts)

        try:
            with ActualParser(db_path) as parser:
                result = parser.get_transfers()
                assert len(result) == 1
                warnings = parser.get_warnings()
                assert len(warnings) == 1
                assert any("mismatch" in w.lower() for w in warnings)
        finally:
            os.unlink(db_path)

    def test_reconstructs_split_transaction(self):
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
            "INSERT INTO categories VALUES ('cat2', 'Chemia', 0, 'g1', 0)",
            # Parent: Biedronka, suma
            "INSERT INTO transactions VALUES ('parent1', 1, 0, NULL, 'acc1', NULL, -8000, NULL, NULL, 20260715, NULL, 0)",
            # Child 1: -5000, Jedzenie
            "INSERT INTO transactions VALUES ('child1', 0, 1, 'parent1', 'acc1', 'cat1', -5000, NULL, NULL, 20260715, NULL, 0)",
            # Child 2: -3000, Chemia
            "INSERT INTO transactions VALUES ('child2', 0, 1, 'parent1', 'acc1', 'cat2', -3000, NULL, NULL, 20260715, NULL, 0)",
        ]
        db_path = _make_actual_db(schema, inserts)

        with ActualParser(db_path) as parser:
            result = parser.get_splits()
            assert len(result) == 1
            txn = result[0]
            assert txn["type"] == "expense"
            assert len(txn["postings"]) == 3  # 1 credit + 2 debits
            # First posting: credit on account for total
            assert txn["postings"][0]["account_actual_id"] == "acc1"
            assert txn["postings"][0]["direction"] == "credit"
            assert txn["postings"][0]["source_amount"] == 8000
            assert txn["postings"][0]["category_actual_id"] is None
            # Second: debit for Jedzenie
            assert txn["postings"][1]["account_actual_id"] == "acc1"
            assert txn["postings"][1]["category_actual_id"] == "cat1"
            assert txn["postings"][1]["direction"] == "debit"
            assert txn["postings"][1]["source_amount"] == 5000
            # Third: debit for Chemia
            assert txn["postings"][2]["account_actual_id"] == "acc1"
            assert txn["postings"][2]["category_actual_id"] == "cat2"
            assert txn["postings"][2]["direction"] == "debit"
            assert txn["postings"][2]["source_amount"] == 3000
            os.unlink(db_path)

    def test_split_with_orphaned_parent(self):
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
            # Parent with no children
            "INSERT INTO transactions VALUES ('parent1', 1, 0, NULL, 'acc1', NULL, -8000, NULL, NULL, 20260715, NULL, 0)",
        ]
        db_path = _make_actual_db(schema, inserts)

        with ActualParser(db_path) as parser:
            result = parser.get_splits()
            assert len(result) == 0
            warnings = parser.get_warnings()
            assert len(warnings) == 1
            assert "no children found" in warnings[0]
            os.unlink(db_path)

    def test_reconstructs_income_split_transaction(self):
        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        CREATE TABLE categories (id TEXT, name TEXT, is_income INTEGER, cat_group TEXT, tombstone INTEGER);
        CREATE TABLE transactions (
            id TEXT, isParent INTEGER, isChild INTEGER, parent_id TEXT,
            acct TEXT, category TEXT, amount INTEGER, description TEXT,
            notes TEXT, date INTEGER, transferred_id TEXT, tombstone INTEGER
        );
        """
        inserts = [
            "INSERT INTO accounts VALUES ('acc1', 'ING', 0, 0, 0)",
            "INSERT INTO categories VALUES ('cat1', 'Pensja', 1, 'g2', 0)",
            "INSERT INTO categories VALUES ('cat2', 'Freelance', 1, 'g2', 0)",
            # Parent: 80 PLN income
            "INSERT INTO transactions VALUES ('parent1', 1, 0, NULL, 'acc1', NULL, 8000, NULL, NULL, 20260715, NULL, 0)",
            # Child 1: 5000, Pensja
            "INSERT INTO transactions VALUES ('child1', 0, 1, 'parent1', 'acc1', 'cat1', 5000, NULL, NULL, 20260715, NULL, 0)",
            # Child 2: 3000, Freelance
            "INSERT INTO transactions VALUES ('child2', 0, 1, 'parent1', 'acc1', 'cat2', 3000, NULL, NULL, 20260715, NULL, 0)",
        ]
        db_path = _make_actual_db(schema, inserts)

        with ActualParser(db_path) as parser:
            result = parser.get_splits()
            assert len(result) == 1
            txn = result[0]
            assert txn["type"] == "income"
            assert len(txn["postings"]) == 3  # 1 debit + 2 credits
            # First posting: debit on account for total
            assert txn["postings"][0]["account_actual_id"] == "acc1"
            assert txn["postings"][0]["direction"] == "debit"
            assert txn["postings"][0]["source_amount"] == 8000
            assert txn["postings"][0]["category_actual_id"] is None
            # Second: credit for Freelance (3000 < 5000, ordered by amount)
            assert txn["postings"][1]["account_actual_id"] == "acc1"
            assert txn["postings"][1]["category_actual_id"] == "cat2"
            assert txn["postings"][1]["direction"] == "credit"
            assert txn["postings"][1]["source_amount"] == 3000
            # Third: credit for Pensja
            assert txn["postings"][2]["account_actual_id"] == "acc1"
            assert txn["postings"][2]["category_actual_id"] == "cat1"
            assert txn["postings"][2]["direction"] == "credit"
            assert txn["postings"][2]["source_amount"] == 5000
            os.unlink(db_path)

    def test_uses_account_currency_in_postings(self):
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
            "INSERT INTO accounts VALUES ('rev_eu', 'Revolut EUR', 0, 0, 0)",
            "INSERT INTO accounts VALUES ('rev_pln', 'Revolut PLN', 0, 0, 0)",
            "INSERT INTO categories VALUES ('cat1', 'Zakupy', 0, 'g1', 0)",
            "INSERT INTO transactions VALUES ('tx1', 0, 0, NULL, 'rev_eu', 'cat1', -500, NULL, NULL, 20260715, NULL, 0)",
            "INSERT INTO transactions VALUES ('tx2', 0, 0, NULL, 'rev_pln', 'cat1', -10000, NULL, NULL, 20260715, NULL, 0)",
        ]
        db_path = _make_actual_db(schema, inserts)

        with ActualParser(db_path) as parser:
            accounts = parser.get_accounts()
            eu_acc = next(a for a in accounts if a["name"] == "Revolut EUR")
            pln_acc = next(a for a in accounts if a["name"] == "Revolut PLN")
            assert eu_acc["currency"] == "EUR"
            assert pln_acc["currency"] == "PLN"

            txns = parser.get_transactions()
            eu_txn = next(t for t in txns if t["actual_id"] == "tx1")
            pln_txn = next(t for t in txns if t["actual_id"] == "tx2")
            assert eu_txn["postings"][0]["source_currency"] == "EUR"
            assert pln_txn["postings"][0]["source_currency"] == "PLN"
        os.unlink(db_path)


import uuid as _uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


class TestNbpRates:
    @pytest.mark.asyncio
    async def test_fetches_eur_rate(self):
        from unittest.mock import MagicMock

        from app.finance.nbp_rates import NbpRateProvider

        provider = NbpRateProvider()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": "EUR",
            "rates": [{"mid": 4.30, "effectiveDate": "2026-07-15"}],
        }

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            rate = await provider.get_rate("EUR", date(2026, 7, 15))
            assert rate == 4.30

    @pytest.mark.asyncio
    async def test_caches_same_day(self):
        from unittest.mock import MagicMock

        from app.finance.nbp_rates import NbpRateProvider

        provider = NbpRateProvider()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": "EUR",
            "rates": [{"mid": 4.30, "effectiveDate": "2026-07-15"}],
        }

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            rate1 = await provider.get_rate("EUR", date(2026, 7, 15))
            rate2 = await provider.get_rate("EUR", date(2026, 7, 15))
            assert rate1 == rate2 == 4.30
            assert mock_get.call_count == 1  # cached

    @pytest.mark.asyncio
    async def test_pln_always_one(self):
        from app.finance.nbp_rates import NbpRateProvider

        provider = NbpRateProvider()
        rate = await provider.get_rate("PLN", date(2026, 7, 15))
        assert rate == 1.0

    def test_calculate_base_amount(self):
        from app.finance.nbp_rates import NbpRateProvider

        provider = NbpRateProvider()
        assert provider.calculate_base_amount(100, 4.30) == 430
        assert provider.calculate_base_amount(50, 4.2678) == 213  # round to int

    @pytest.mark.asyncio
    async def test_error_returns_zero_and_not_cached(self):
        from app.finance.nbp_rates import NbpRateProvider

        provider = NbpRateProvider()
        mock_response = AsyncMock()
        mock_response.raise_for_status.side_effect = RuntimeError("network error")

        with patch("httpx.AsyncClient.get", return_value=mock_response) as mock_get:
            rate = await provider.get_rate("USD", date(2026, 7, 15))
            assert rate == 0.0
            rate2 = await provider.get_rate("USD", date(2026, 7, 15))
            assert rate2 == 0.0
            assert mock_get.call_count == 2


class TestFxEnrichment:
    @pytest.mark.asyncio
    async def test_enriches_eur_postings_with_nbp_rate(self):
        from unittest.mock import MagicMock

        from app.finance.nbp_rates import NbpRateProvider

        provider = NbpRateProvider()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": "EUR",
            "rates": [{"mid": 4.2856, "effectiveDate": "2026-07-15"}],
        }

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            base_amount = provider.calculate_base_amount(
                500, await provider.get_rate("EUR", date(2026, 7, 15))
            )
            assert base_amount == 2143  # 5.00 * 4.2856 = 21.428 -> round to 2143 groszy

    @pytest.mark.asyncio
    async def test_pln_postings_unchanged(self):
        from app.finance.nbp_rates import NbpRateProvider

        provider = NbpRateProvider()
        rate = await provider.get_rate("PLN", date(2026, 7, 15))
        base_amount = provider.calculate_base_amount(10000, rate)
        assert rate == 1.0
        assert base_amount == 10000


class TestMigrationPostings:
    def test_expense_uses_account_and_category_sides(self):
        from scripts.migrate_actual import build_pa_postings

        account_id = _uuid.uuid4()
        category_id = _uuid.uuid4()
        transaction = {
            "actual_id": "expense-1",
            "date": date(2026, 7, 15),
            "type": "expense",
            "postings": [
                {
                    "account_actual_id": "account-1",
                    "category_actual_id": None,
                    "source_amount": 5000,
                    "source_currency": "PLN",
                    "direction": "credit",
                },
                {
                    "account_actual_id": "account-1",
                    "category_actual_id": "category-1",
                    "source_amount": 5000,
                    "source_currency": "PLN",
                    "direction": "debit",
                },
            ],
        }

        postings = build_pa_postings(
            transaction,
            {"account-1": account_id},
            {"category-1": category_id},
            {"account-1": "PLN"},
            {},
            {"account-1": False},
        )

        assert [(posting.account_id, posting.category_id) for posting in postings] == [
            (account_id, None),
            (None, category_id),
        ]
        assert all(posting.is_budget_impact is False for posting in postings)
        assert (
            sum(
                posting.base_amount_pln
                if posting.direction == "debit"
                else -posting.base_amount_pln
                for posting in postings
            )
            == 0
        )

    def test_eur_posting_uses_verified_nbp_rate(self):
        from scripts.migrate_actual import build_pa_postings

        account_id = _uuid.uuid4()
        category_id = _uuid.uuid4()
        transaction = {
            "actual_id": "expense-eur",
            "date": date(2026, 7, 15),
            "type": "expense",
            "postings": [
                {
                    "account_actual_id": "account-eur",
                    "category_actual_id": None,
                    "source_amount": 500,
                    "source_currency": "EUR",
                    "direction": "credit",
                },
                {
                    "account_actual_id": "account-eur",
                    "category_actual_id": "category-1",
                    "source_amount": 500,
                    "source_currency": "EUR",
                    "direction": "debit",
                },
            ],
        }

        postings = build_pa_postings(
            transaction,
            {"account-eur": account_id},
            {"category-1": category_id},
            {"account-eur": "EUR"},
            {("EUR", date(2026, 7, 15)): 4.2856},
        )

        assert [posting.base_amount_pln for posting in postings] == [2143, 2143]
        assert all(posting.fx_rate == 4.2856 for posting in postings)
        assert all(posting.fx_rate_source == "nbp" for posting in postings)

    def test_missing_usd_rate_rejects_entire_transaction(self):
        from scripts.migrate_actual import ImportValidationError, build_pa_postings

        transaction = {
            "actual_id": "expense-usd",
            "date": date(2026, 7, 15),
            "type": "expense",
            "postings": [
                {
                    "account_actual_id": "account-usd",
                    "category_actual_id": None,
                    "source_amount": 500,
                    "source_currency": "USD",
                    "direction": "credit",
                },
                {
                    "account_actual_id": "account-usd",
                    "category_actual_id": "category-1",
                    "source_amount": 500,
                    "source_currency": "USD",
                    "direction": "debit",
                },
            ],
        }

        with pytest.raises(ImportValidationError, match="Missing FX rate: USD on 2026-07-15"):
            build_pa_postings(
                transaction,
                {"account-usd": _uuid.uuid4()},
                {"category-1": _uuid.uuid4()},
                {"account-usd": "USD"},
                {("USD", date(2026, 7, 15)): 0.0},
            )

    def test_cross_currency_transfer_adds_non_budget_fx_difference_posting(self):
        from scripts.migrate_actual import build_pa_postings

        pln_account_id = _uuid.uuid4()
        usd_account_id = _uuid.uuid4()
        loss_category_id = _uuid.uuid4()
        transaction = {
            "actual_id": "transfer-usd-pln",
            "date": date(2026, 7, 15),
            "type": "transfer",
            "postings": [
                {
                    "account_actual_id": "account-usd",
                    "category_actual_id": None,
                    "source_amount": 10000,
                    "source_currency": "USD",
                    "direction": "credit",
                },
                {
                    "account_actual_id": "account-pln",
                    "category_actual_id": None,
                    "source_amount": 43000,
                    "source_currency": "PLN",
                    "direction": "debit",
                },
            ],
        }

        postings = build_pa_postings(
            transaction,
            {"account-usd": usd_account_id, "account-pln": pln_account_id},
            {},
            {"account-usd": "USD", "account-pln": "PLN"},
            {("USD", date(2026, 7, 15)): 4.2856},
            fx_category_ids={"loss": loss_category_id},
        )

        assert [(posting.source_amount, posting.source_currency) for posting in postings[:2]] == [
            (10000, "USD"),
            (43000, "PLN"),
        ]
        assert postings[2].account_id is None
        assert postings[2].category_id == loss_category_id
        assert postings[2].direction == "debit"
        assert postings[2].base_amount_pln == 144
        assert postings[2].is_budget_impact is False
        assert (
            sum(
                posting.base_amount_pln
                if posting.direction == "debit"
                else -posting.base_amount_pln
                for posting in postings
            )
            == 0
        )

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_ordinary_pln_transaction_uses_account_and_category_sides(self, db_session):
        from app.finance.schemas import AccountCreate, CategoryCreate, TransactionCreate
        from app.finance.service import create_account, create_category, create_transaction
        from scripts.migrate_actual import build_pa_postings

        user_id = _uuid.uuid4()
        account = await create_account(
            db_session, user_id, AccountCreate(name="ING", type="checking")
        )
        category = await create_category(
            db_session, user_id, CategoryCreate(name="Paliwo", type="expense")
        )
        transaction = {
            "actual_id": "expense-1",
            "date": date(2026, 7, 15),
            "type": "expense",
            "postings": [
                {
                    "account_actual_id": "account-1",
                    "category_actual_id": None,
                    "source_amount": 5000,
                    "direction": "credit",
                },
                {
                    "account_actual_id": "account-1",
                    "category_actual_id": "category-1",
                    "source_amount": 5000,
                    "direction": "debit",
                },
            ],
        }
        postings = build_pa_postings(
            transaction,
            {"account-1": account.id},
            {"category-1": category.id},
            {"account-1": "PLN"},
            {},
        )

        await create_transaction(
            db_session,
            user_id,
            TransactionCreate(
                transaction_date=transaction["date"],
                description="[actual:expense-1] Paliwo",
                type="expense",
                source="actual",
                postings=postings,
            ),
        )

        assert [(posting.account_id, posting.category_id) for posting in postings] == [
            (account.id, None),
            (None, category.id),
        ]


class TestMigrationPipeline:
    pytestmark = pytest.mark.integration

    @pytest.mark.asyncio
    async def test_legacy_actual_transactions_backfill_account_category_and_group_mappings(
        self, db_session, monkeypatch
    ):
        from sqlalchemy import func, select

        from app.finance.models import (
            Account,
            ActualImportMapping,
            Category,
            FinancialTransaction,
            Posting,
        )
        from app.finance.schemas import AccountCreate, CategoryCreate
        from app.finance.service import create_account, create_category
        from scripts import migrate_actual

        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        CREATE TABLE categories (id TEXT, name TEXT, is_income INTEGER, cat_group TEXT, tombstone INTEGER);
        CREATE TABLE category_groups (id TEXT, name TEXT, tombstone INTEGER);
        CREATE TABLE transactions (
            id TEXT, isParent INTEGER, isChild INTEGER, parent_id TEXT,
            acct TEXT, category TEXT, amount INTEGER, description TEXT,
            notes TEXT, date INTEGER, transferred_id TEXT, tombstone INTEGER
        );
        CREATE TABLE payees (id TEXT, name TEXT);
        CREATE TABLE payee_mapping (id TEXT, targetId TEXT, payeeId TEXT);
        """
        db_path = _make_actual_db(
            schema,
            [
                "INSERT INTO accounts VALUES ('acc1', 'Actual ING', 0, 0, 0)",
                "INSERT INTO category_groups VALUES ('group1', 'Actual Transport', 0)",
                "INSERT INTO categories VALUES ('fuel', 'Actual Paliwo', 0, 'group1', 0)",
                "INSERT INTO transactions VALUES ('tx1', 0, 0, NULL, 'acc1', 'fuel', -5000, NULL, NULL, 20260814, NULL, 0)",
            ],
        )
        user_id = _uuid.uuid4()
        account = await create_account(
            db_session, user_id, AccountCreate(name="Legacy account", type="checking")
        )
        group = await create_category(
            db_session, user_id, CategoryCreate(name="Legacy group", type="expense")
        )
        category = await create_category(
            db_session,
            user_id,
            CategoryCreate(name="Legacy category", type="expense", parent_id=group.id),
        )
        transaction = FinancialTransaction(
            user_id=user_id,
            date=date(2026, 8, 14),
            description="[actual:tx1] Legacy expense",
            type="expense",
            source="actual",
        )
        db_session.add(transaction)
        await db_session.flush()
        db_session.add_all(
            [
                Posting(
                    transaction_id=transaction.id,
                    account_id=account.id,
                    source_amount=5000,
                    source_currency="PLN",
                    base_amount_pln=5000,
                    fx_rate=1.0,
                    fx_rate_source="manual",
                    direction="credit",
                ),
                Posting(
                    transaction_id=transaction.id,
                    account_id=account.id,
                    category_id=category.id,
                    source_amount=5000,
                    source_currency="PLN",
                    base_amount_pln=5000,
                    fx_rate=1.0,
                    fx_rate_source="manual",
                    direction="debit",
                ),
            ]
        )
        await db_session.flush()

        class SessionContext:
            async def __aenter__(self):
                return db_session

            async def __aexit__(self, exc_type, exc, traceback):
                return None

        monkeypatch.setattr(migrate_actual, "extract_sqlite", AsyncMock(return_value=db_path))
        monkeypatch.setattr(migrate_actual, "async_session_factory", SessionContext)
        monkeypatch.setattr(
            migrate_actual,
            "NbpRateProvider",
            lambda: SimpleNamespace(close=AsyncMock()),
        )

        try:
            await migrate_actual.migrate(Path("unused"), user_id)
            counts = [
                await db_session.scalar(
                    select(func.count(model.id)).where(model.user_id == user_id)
                )
                for model in (Account, Category, FinancialTransaction, ActualImportMapping)
            ]
            assert counts == [1, 2, 1, 4]
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_unresolved_legacy_actual_mapping_fails_without_creating_entities(
        self, db_session, monkeypatch
    ):
        from sqlalchemy import func, select

        from app.finance.models import Account, Category, FinancialTransaction, Posting
        from app.finance.schemas import AccountCreate, CategoryCreate
        from app.finance.service import create_account, create_category
        from scripts import migrate_actual

        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        CREATE TABLE categories (id TEXT, name TEXT, is_income INTEGER, cat_group TEXT, tombstone INTEGER);
        CREATE TABLE category_groups (id TEXT, name TEXT, tombstone INTEGER);
        CREATE TABLE transactions (
            id TEXT, isParent INTEGER, isChild INTEGER, parent_id TEXT,
            acct TEXT, category TEXT, amount INTEGER, description TEXT,
            notes TEXT, date INTEGER, transferred_id TEXT, tombstone INTEGER
        );
        CREATE TABLE payees (id TEXT, name TEXT);
        CREATE TABLE payee_mapping (id TEXT, targetId TEXT, payeeId TEXT);
        """
        db_path = _make_actual_db(
            schema,
            [
                "INSERT INTO accounts VALUES ('acc1', 'Actual ING', 0, 0, 0)",
                "INSERT INTO accounts VALUES ('acc2', 'Actual Cash', 0, 0, 0)",
                "INSERT INTO category_groups VALUES ('group1', 'Actual Transport', 0)",
                "INSERT INTO categories VALUES ('fuel', 'Actual Paliwo', 0, 'group1', 0)",
                "INSERT INTO transactions VALUES ('tx1', 0, 0, NULL, 'acc1', 'fuel', -5000, NULL, NULL, 20260814, NULL, 0)",
            ],
        )
        user_id = _uuid.uuid4()
        account = await create_account(
            db_session, user_id, AccountCreate(name="Legacy account", type="checking")
        )
        category = await create_category(
            db_session, user_id, CategoryCreate(name="Legacy category", type="expense")
        )
        transaction = FinancialTransaction(
            user_id=user_id,
            date=date(2026, 8, 14),
            description="[actual:tx1] Legacy expense",
            type="expense",
            source="actual",
        )
        db_session.add(transaction)
        await db_session.flush()
        db_session.add_all(
            [
                Posting(
                    transaction_id=transaction.id,
                    account_id=account.id,
                    source_amount=5000,
                    source_currency="PLN",
                    base_amount_pln=5000,
                    fx_rate=1.0,
                    fx_rate_source="manual",
                    direction="credit",
                ),
                Posting(
                    transaction_id=transaction.id,
                    account_id=account.id,
                    category_id=category.id,
                    source_amount=5000,
                    source_currency="PLN",
                    base_amount_pln=5000,
                    fx_rate=1.0,
                    fx_rate_source="manual",
                    direction="debit",
                ),
            ]
        )
        await db_session.flush()

        class SessionContext:
            async def __aenter__(self):
                return db_session

            async def __aexit__(self, exc_type, exc, traceback):
                return None

        monkeypatch.setattr(migrate_actual, "extract_sqlite", AsyncMock(return_value=db_path))
        monkeypatch.setattr(migrate_actual, "async_session_factory", SessionContext)
        monkeypatch.setattr(
            migrate_actual,
            "NbpRateProvider",
            lambda: SimpleNamespace(close=AsyncMock()),
        )

        try:
            with pytest.raises(migrate_actual.LegacyActualMappingError, match="acc2"):
                await migrate_actual.migrate(Path("unused"), user_id)
            counts = [
                await db_session.scalar(
                    select(func.count(model.id)).where(model.user_id == user_id)
                )
                for model in (Account, Category, FinancialTransaction)
            ]
            assert counts == [1, 1, 1]
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_imported_expense_decreases_and_income_increases_account_balance(
        self, db_session, monkeypatch
    ):
        from app.finance.service import get_accounts, get_category_summary, get_financial_summary
        from scripts import migrate_actual

        actual_date = datetime.now(UTC).date().strftime("%Y%m%d")

        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        CREATE TABLE categories (id TEXT, name TEXT, is_income INTEGER, cat_group TEXT, tombstone INTEGER);
        CREATE TABLE category_groups (id TEXT, name TEXT, tombstone INTEGER);
        CREATE TABLE transactions (
            id TEXT, isParent INTEGER, isChild INTEGER, parent_id TEXT,
            acct TEXT, category TEXT, amount INTEGER, description TEXT,
            notes TEXT, date INTEGER, transferred_id TEXT, tombstone INTEGER
        );
        CREATE TABLE payees (id TEXT, name TEXT);
        CREATE TABLE payee_mapping (id TEXT, targetId TEXT, payeeId TEXT);
        """
        expense_db_path = _make_actual_db(
            schema,
            [
                "INSERT INTO accounts VALUES ('acc1', 'ING', 0, 0, 0)",
                "INSERT INTO category_groups VALUES ('expense-group', 'Wydatki', 0)",
                "INSERT INTO categories VALUES ('expense-cat', 'Paliwo', 0, 'expense-group', 0)",
                f"INSERT INTO transactions VALUES ('expense', 0, 0, NULL, 'acc1', 'expense-cat', -5000, NULL, NULL, {actual_date}, NULL, 0)",
            ],
        )
        income_db_path = _make_actual_db(
            schema,
            [
                "INSERT INTO accounts VALUES ('acc1', 'ING', 0, 0, 0)",
                "INSERT INTO category_groups VALUES ('income-group', 'Przychody', 0)",
                "INSERT INTO categories VALUES ('income-cat', 'Pensja', 1, 'income-group', 0)",
                f"INSERT INTO transactions VALUES ('income', 0, 0, NULL, 'acc1', 'income-cat', 12000, NULL, NULL, {actual_date}, NULL, 0)",
            ],
        )
        user_id = _uuid.uuid4()

        class SessionContext:
            async def __aenter__(self):
                return db_session

            async def __aexit__(self, exc_type, exc, traceback):
                return None

        monkeypatch.setattr(
            migrate_actual,
            "extract_sqlite",
            AsyncMock(side_effect=[expense_db_path, income_db_path]),
        )
        monkeypatch.setattr(migrate_actual, "async_session_factory", SessionContext)
        monkeypatch.setattr(
            migrate_actual,
            "NbpRateProvider",
            lambda: SimpleNamespace(close=AsyncMock()),
        )

        try:
            await migrate_actual.migrate(Path("unused"), user_id)
            accounts = await get_accounts(db_session, user_id)
            assert [(account.name, account.balance_pln) for account in accounts] == [("ING", -5000)]
            await migrate_actual.migrate(Path("unused"), user_id)
            accounts = await get_accounts(db_session, user_id)
            assert [(account.name, account.balance_pln) for account in accounts] == [("ING", 7000)]
            financial_summary = await get_financial_summary(db_session, user_id)
            category_summary = await get_category_summary(db_session, user_id)
            assert [
                (account["name"], account["balance_pln"]) for account in financial_summary.accounts
            ] == [("ING", 7000)]
            assert financial_summary.income_total_pln == 12000
            assert financial_summary.expense_total_pln == 5000
            assert [
                (category.name, category.total_pln) for category in category_summary.categories
            ] == [("Paliwo", 5000)]
            assert [(group.name, group.total_pln) for group in category_summary.groups] == [
                ("Wydatki", 5000)
            ]
        finally:
            os.unlink(expense_db_path)
            os.unlink(income_db_path)

    @pytest.mark.asyncio
    async def test_duplicate_actual_mapping_keeps_session_usable(self, db_session):
        from sqlalchemy import select

        from app.finance.models import ActualImportMapping
        from app.finance.schemas import AccountCreate
        from app.finance.service import create_account
        from scripts.migrate_actual import _store_mapping

        user_id = _uuid.uuid4()
        first_account = await create_account(
            db_session, user_id, AccountCreate(name="Pierwsze", type="checking")
        )
        second_account = await create_account(
            db_session, user_id, AccountCreate(name="Drugie", type="checking")
        )

        await _store_mapping(db_session, user_id, "account", "actual-account", first_account.id)
        await _store_mapping(db_session, user_id, "account", "actual-account", second_account.id)
        third_account = await create_account(
            db_session, user_id, AccountCreate(name="Trzecie", type="checking")
        )
        mapping = await db_session.scalar(
            select(ActualImportMapping).where(
                ActualImportMapping.user_id == user_id,
                ActualImportMapping.entity_type == "account",
                ActualImportMapping.actual_id == "actual-account",
            )
        )

        assert mapping is not None
        assert mapping.entity_id == first_account.id
        assert third_account.id

    @pytest.mark.asyncio
    async def test_second_import_reuses_actual_accounts_categories_and_transactions(
        self, db_session, monkeypatch
    ):
        from sqlalchemy import func, select

        from app.finance.models import Account, Category, FinancialTransaction
        from scripts import migrate_actual

        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        CREATE TABLE categories (id TEXT, name TEXT, is_income INTEGER, cat_group TEXT, tombstone INTEGER);
        CREATE TABLE category_groups (id TEXT, name TEXT, tombstone INTEGER);
        CREATE TABLE transactions (
            id TEXT, isParent INTEGER, isChild INTEGER, parent_id TEXT,
            acct TEXT, category TEXT, amount INTEGER, description TEXT,
            notes TEXT, date INTEGER, transferred_id TEXT, tombstone INTEGER
        );
        CREATE TABLE payees (id TEXT, name TEXT);
        CREATE TABLE payee_mapping (id TEXT, targetId TEXT, payeeId TEXT);
        """
        db_path = _make_actual_db(
            schema,
            [
                "INSERT INTO accounts VALUES ('acc1', 'ING', 0, 0, 0)",
                "INSERT INTO category_groups VALUES ('group1', 'Transport', 0)",
                "INSERT INTO categories VALUES ('fuel', 'Paliwo', 0, 'group1', 0)",
                "INSERT INTO transactions VALUES ('expense', 0, 0, NULL, 'acc1', 'fuel', -5000, NULL, NULL, 20260715, NULL, 0)",
            ],
        )
        user_id = _uuid.uuid4()

        class SessionContext:
            async def __aenter__(self):
                return db_session

            async def __aexit__(self, exc_type, exc, traceback):
                return None

        monkeypatch.setattr(migrate_actual, "extract_sqlite", AsyncMock(return_value=db_path))
        monkeypatch.setattr(migrate_actual, "async_session_factory", SessionContext)
        monkeypatch.setattr(
            migrate_actual,
            "NbpRateProvider",
            lambda: SimpleNamespace(close=AsyncMock()),
        )

        try:
            await migrate_actual.migrate(Path("unused"), user_id)
            await migrate_actual.migrate(Path("unused"), user_id)
            counts = [
                await db_session.scalar(
                    select(func.count(model.id)).where(model.user_id == user_id)
                )
                for model in (Account, Category, FinancialTransaction)
            ]
            assert counts == [1, 2, 1]
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_import_does_not_reuse_manual_records_with_matching_names(
        self, db_session, monkeypatch
    ):
        from sqlalchemy import func, select

        from app.finance.models import Account, Category
        from app.finance.schemas import AccountCreate, CategoryCreate
        from app.finance.service import create_account, create_category
        from scripts import migrate_actual

        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        CREATE TABLE categories (id TEXT, name TEXT, is_income INTEGER, cat_group TEXT, tombstone INTEGER);
        CREATE TABLE category_groups (id TEXT, name TEXT, tombstone INTEGER);
        CREATE TABLE transactions (
            id TEXT, isParent INTEGER, isChild INTEGER, parent_id TEXT,
            acct TEXT, category TEXT, amount INTEGER, description TEXT,
            notes TEXT, date INTEGER, transferred_id TEXT, tombstone INTEGER
        );
        CREATE TABLE payees (id TEXT, name TEXT);
        CREATE TABLE payee_mapping (id TEXT, targetId TEXT, payeeId TEXT);
        """
        db_path = _make_actual_db(
            schema,
            [
                "INSERT INTO accounts VALUES ('acc1', 'ING', 0, 0, 0)",
                "INSERT INTO category_groups VALUES ('group1', 'Transport', 0)",
                "INSERT INTO categories VALUES ('fuel', 'Paliwo', 0, 'group1', 0)",
                "INSERT INTO transactions VALUES ('expense', 0, 0, NULL, 'acc1', 'fuel', -5000, NULL, NULL, 20260715, NULL, 0)",
            ],
        )
        user_id = _uuid.uuid4()
        await create_account(db_session, user_id, AccountCreate(name="ING", type="checking"))
        await create_category(db_session, user_id, CategoryCreate(name="Paliwo", type="expense"))

        class SessionContext:
            async def __aenter__(self):
                return db_session

            async def __aexit__(self, exc_type, exc, traceback):
                return None

        monkeypatch.setattr(migrate_actual, "extract_sqlite", AsyncMock(return_value=db_path))
        monkeypatch.setattr(migrate_actual, "async_session_factory", SessionContext)
        monkeypatch.setattr(
            migrate_actual,
            "NbpRateProvider",
            lambda: SimpleNamespace(close=AsyncMock()),
        )

        try:
            await migrate_actual.migrate(Path("unused"), user_id)
            await migrate_actual.migrate(Path("unused"), user_id)
            counts = [
                await db_session.scalar(
                    select(func.count(model.id)).where(model.user_id == user_id)
                )
                for model in (Account, Category)
            ]
            assert counts == [2, 3]
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_resolve_ids_creates_category_groups_before_children(self, db_session):
        from sqlalchemy import select

        from scripts.migrate_actual import resolve_ids

        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        CREATE TABLE categories (id TEXT, name TEXT, is_income INTEGER, cat_group TEXT, tombstone INTEGER);
        CREATE TABLE category_groups (id TEXT, name TEXT, tombstone INTEGER);
        """
        db_path = _make_actual_db(
            schema,
            [
                "INSERT INTO accounts VALUES ('acc1', 'ING', 1, 0, 0)",
                "INSERT INTO category_groups VALUES ('group1', 'Transport', 0)",
                "INSERT INTO categories VALUES ('fuel', 'Paliwo', 0, 'group1', 0)",
            ],
        )

        user_id = _uuid.uuid4()
        try:
            with ActualParser(db_path) as parser:
                account_map, category_map, _, budget_account_map = await resolve_ids(
                    db_session, user_id, parser
                )
            categories = (
                (await db_session.execute(select(Category).where(Category.user_id == user_id)))
                .scalars()
                .all()
            )
            by_id = {category.id: category for category in categories}

            assert budget_account_map == {"acc1": False}
            assert account_map["acc1"]
            assert by_id[category_map["fuel"]].parent_id is not None
            assert by_id[by_id[category_map["fuel"]].parent_id].name == "Transport"
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_full_import_does_not_create_opening_balance_transactions(
        self, db_session, monkeypatch
    ):
        from sqlalchemy import select

        from app.finance.models import FinancialTransaction
        from scripts import migrate_actual

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
        db_path = _make_actual_db(
            schema,
            [
                "INSERT INTO accounts VALUES ('acc1', 'ING', 0, 0, 0)",
                "INSERT INTO categories VALUES ('cat1', 'Jedzenie', 0, 'g1', 0)",
                "INSERT INTO transactions VALUES ('tx1', 0, 0, NULL, 'acc1', 'cat1', -5000, 'Zakupy', NULL, 20260701, NULL, 0)",
            ],
        )

        class SessionContext:
            async def __aenter__(self):
                return db_session

            async def __aexit__(self, exc_type, exc, traceback):
                return None

        opening_balances = AsyncMock()
        monkeypatch.setattr(migrate_actual, "extract_sqlite", AsyncMock(return_value=db_path))
        monkeypatch.setattr(migrate_actual, "async_session_factory", SessionContext)
        monkeypatch.setattr(
            migrate_actual, "create_opening_balances", opening_balances, raising=False
        )
        monkeypatch.setattr(
            migrate_actual,
            "NbpRateProvider",
            lambda: SimpleNamespace(close=AsyncMock()),
        )

        try:
            await migrate_actual.migrate(Path("unused"), _uuid.uuid4())
        finally:
            os.unlink(db_path)

        opening_balances.assert_not_awaited()
        transactions = (await db_session.execute(select(FinancialTransaction))).scalars().all()
        assert all(not transaction.description.startswith("[BO]") for transaction in transactions)

    @pytest.mark.asyncio
    async def test_full_pipeline_dry_run(self, db_session):
        """Full pipeline with synthetic data, writes to test DB."""
        from app.finance.schemas import (
            AccountCreate,
            CategoryCreate,
            PostingCreate,
            TransactionCreate,
        )
        from app.finance.service import (
            create_account,
            create_category,
            create_transaction,
            get_transactions,
        )

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
            "INSERT INTO categories VALUES ('cat2', 'Pensja', 1, 'g2', 0)",
            "INSERT INTO payees VALUES ('pay1', 'Biedronka')",
            "INSERT INTO payees VALUES ('pay2', 'Wyplata')",
            "INSERT INTO payee_mapping VALUES ('pm1', 'tx1', 'pay1')",
            "INSERT INTO payee_mapping VALUES ('pm2', 'tx2', 'pay2')",
            "INSERT INTO transactions VALUES ('tx1', 0, 0, NULL, 'acc1', 'cat1', -5000, 'pm1', NULL, 20260701, NULL, 0)",
            "INSERT INTO transactions VALUES ('tx2', 0, 0, NULL, 'acc1', 'cat2', 500000, 'pm2', NULL, 20260701, NULL, 0)",
            "INSERT INTO transactions VALUES ('tx_a', 0, 0, NULL, 'acc1', NULL, -20000, NULL, NULL, 20260701, 'tx_b', 0)",
            "INSERT INTO transactions VALUES ('tx_b', 0, 0, NULL, 'acc2', NULL, 20000, NULL, NULL, 20260701, 'tx_a', 0)",
            "INSERT INTO transactions VALUES ('parent1', 1, 0, NULL, 'acc1', NULL, -10000, NULL, NULL, 20260701, NULL, 0)",
            "INSERT INTO transactions VALUES ('child1', 0, 1, 'parent1', 'acc1', 'cat1', -6000, NULL, NULL, 20260701, NULL, 0)",
            "INSERT INTO transactions VALUES ('child2', 0, 1, 'parent1', 'acc1', 'cat1', -4000, NULL, NULL, 20260701, NULL, 0)",
        ]
        db_path = _make_actual_db(schema, inserts)

        parser = ActualParser(db_path)
        accounts = parser.get_accounts()
        categories = parser.get_categories()
        transactions = parser.get_transactions()
        transfers = parser.get_transfers()
        splits = parser.get_splits()

        assert len(accounts) == 2
        assert len(categories) == 2
        assert len(transactions) == 2
        assert len(transfers) == 1
        assert len(splits) == 1

        all_txns = transactions + transfers + splits
        for txn in all_txns:
            total = 0
            for p in txn["postings"]:
                signed = p["source_amount"] if p["direction"] == "debit" else -p["source_amount"]
                total += signed
            assert total == 0, f"Transaction {txn['actual_id']} not balanced: {total}"

        user_id = _uuid.uuid4()
        acct_map = {}
        for a in accounts:
            pa_a = await create_account(
                db_session,
                user_id,
                AccountCreate(
                    name=a["name"],
                    type=a["type"],
                    currency=a["currency"],
                ),
            )
            acct_map[a["actual_id"]] = pa_a.id

        cat_map = {}
        for c in categories:
            pa_c = await create_category(
                db_session,
                user_id,
                CategoryCreate(
                    name=c["name"],
                    type=c["type"],
                ),
            )
            cat_map[c["actual_id"]] = pa_c.id

        written = 0
        for txn in all_txns:
            postings = []
            for p in txn["postings"]:
                postings.append(
                    PostingCreate(
                        account_id=acct_map[p["account_actual_id"]],
                        category_id=cat_map.get(p.get("category_actual_id"))
                        if p.get("category_actual_id")
                        else None,
                        source_amount=p["source_amount"],
                        source_currency=p["source_currency"],
                        base_amount_pln=p["source_amount"],
                        fx_rate=1.0,
                        fx_rate_source="manual",
                        direction=p["direction"],
                    )
                )
            await create_transaction(
                db_session,
                user_id,
                TransactionCreate(
                    transaction_date=txn["date"],
                    description=f"[actual:{txn['actual_id']}] {txn['description']}",
                    type=txn["type"],
                    source="actual",
                    postings=postings,
                ),
            )
            written += 1

        assert written == 4

        db_txns = await get_transactions(db_session, user_id, limit=100)
        assert len(db_txns) == 4

        os.unlink(db_path)
