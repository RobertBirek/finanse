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

    def test_transfer_with_warnings(self):
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
            # 3 rows with same transferred_id — unpaired
            "INSERT INTO transactions VALUES ('tx_a', 0, 0, NULL, 'acc_ing', NULL, -5000, NULL, NULL, 20260701, 'link_bad', 0)",
            "INSERT INTO transactions VALUES ('tx_b', 0, 0, NULL, 'acc_cash', NULL, 5000, NULL, NULL, 20260701, 'link_bad', 0)",
            "INSERT INTO transactions VALUES ('tx_c', 0, 0, NULL, 'acc_ing', NULL, -2000, NULL, NULL, 20260701, 'link_bad', 0)",
            # Both rows positive — mismatched signs
            "INSERT INTO transactions VALUES ('tx_d', 0, 0, NULL, 'acc_ing', NULL, 3000, NULL, NULL, 20260701, 'link_both_pos', 0)",
            "INSERT INTO transactions VALUES ('tx_e', 0, 0, NULL, 'acc_cash', NULL, 3000, NULL, NULL, 20260701, 'link_both_pos', 0)",
        ]
        db_path = _make_actual_db(schema, inserts)

        try:
            with ActualParser(db_path) as parser:
                result = parser.get_transfers()
                assert len(result) == 0
                warnings = parser.get_warnings()
                assert len(warnings) == 2
                assert any("link_bad" in w and "3 rows" in w for w in warnings)
                assert any("link_both_pos" in w and "both rows same sign" in w for w in warnings)
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


import pytest
from unittest.mock import AsyncMock, patch
from datetime import date


class TestNbpRates:
    @pytest.mark.asyncio
    async def test_fetches_eur_rate(self):
        from app.finance.nbp_rates import NbpRateProvider
        from unittest.mock import MagicMock

        provider = NbpRateProvider()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": "EUR",
            "rates": [{"mid": 4.30, "effectiveDate": "2026-07-15"}]
        }

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            rate = await provider.get_rate("EUR", date(2026, 7, 15))
            assert rate == 4.30

    @pytest.mark.asyncio
    async def test_caches_same_day(self):
        from app.finance.nbp_rates import NbpRateProvider
        from unittest.mock import MagicMock

        provider = NbpRateProvider()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": "EUR",
            "rates": [{"mid": 4.30, "effectiveDate": "2026-07-15"}]
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
