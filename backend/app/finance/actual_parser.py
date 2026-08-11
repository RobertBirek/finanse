import sqlite3
from datetime import date
from pathlib import Path
from typing import TypedDict


class AccountDict(TypedDict):
    actual_id: str
    name: str
    type: str
    currency: str


class CategoryDict(TypedDict):
    actual_id: str
    name: str
    type: str


class ActualParser:
    def __init__(self, db_path: Path | str):
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row

    def _detect_currency(self, name: str) -> str:
        name_lower = name.lower()
        if "eu" in name_lower or "eur" in name_lower:
            return "EUR"
        if "usd" in name_lower:
            return "USD"
        return "PLN"

    def get_accounts(self) -> list[AccountDict]:
        rows = self._conn.execute(
            "SELECT id, name, offbudget FROM accounts WHERE tombstone=0 AND closed=0"
        ).fetchall()
        return [
            {
                "actual_id": r["id"],
                "name": r["name"],
                "type": "savings" if r["offbudget"] else "checking",
                "currency": self._detect_currency(r["name"]),
            }
            for r in rows
        ]

    def get_categories(self) -> list[CategoryDict]:
        rows = self._conn.execute(
            "SELECT id, name, is_income FROM categories WHERE tombstone=0"
        ).fetchall()
        return [
            {
                "actual_id": r["id"],
                "name": r["name"],
                "type": "income" if r["is_income"] else "expense",
            }
            for r in rows
        ]
