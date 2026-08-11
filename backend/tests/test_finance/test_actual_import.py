import sqlite3
import tempfile
from pathlib import Path
from datetime import date

from app.finance.actual_parser import ActualParser


def _make_actual_db(schema_sql: str, inserts: list[str]) -> Path:
    """Helper: create in-memory SQLite, dump to temp file."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(schema_sql)
    for stmt in inserts:
        conn.execute(stmt)
    conn.commit()
    tmp = Path(tempfile.mktemp(suffix=".sqlite"))
    src = sqlite3.connect(str(tmp))
    conn.backup(src)
    conn.close()
    src.close()
    return tmp


class TestActualParserAccounts:
    def test_reads_active_accounts(self):
        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        """
        inserts = [
            "INSERT INTO accounts VALUES ('a1', 'ING', 0, 0, 0)",
            "INSERT INTO accounts VALUES ('a2', 'Gotowka', 1, 0, 0)",
            "INSERT INTO accounts VALUES ('a3', 'Zamkniete', 0, 1, 0)",  # closed
            "INSERT INTO accounts VALUES ('a4', 'Usuniete', 0, 0, 1)",   # tombstone
        ]
        db_path = _make_actual_db(schema, inserts)

        parser = ActualParser(db_path)
        result = parser.get_accounts()

        assert len(result) == 2  # only active, non-tombstone
        assert result[0]["name"] == "ING"
        assert result[0]["type"] == "checking"  # offbudget=0
        assert result[1]["name"] == "Gotowka"
        assert result[1]["type"] == "savings"   # offbudget=1


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
            "INSERT INTO categories VALUES ('c3', 'Ukryta', 0, 'g1', 1)",  # tombstone
        ]
        db_path = _make_actual_db(schema, inserts)

        parser = ActualParser(db_path)
        result = parser.get_categories()

        assert len(result) == 2
        assert result[0]["name"] == "Jedzenie"
        assert result[0]["type"] == "expense"
        assert result[1]["name"] == "Pensja"
        assert result[1]["type"] == "income"
