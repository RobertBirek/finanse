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
